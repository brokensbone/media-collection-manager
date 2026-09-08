{
  description = "wantlist: a self-hosted music want-list";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
    in
    {
      packages = forAllSystems (system:
        let
          pkgs = import nixpkgs { inherit system; };
          lib = pkgs.lib;
          python = pkgs.python312;
          pythonPackages = python.pkgs;
          fastapi = pythonPackages.fastapi.overridePythonAttrs (_: { doCheck = false; });
          # APScheduler 3.11.2's upstream process-pool tests are flaky under the current
          # sandboxed Python build. Wantlist's own tests cover its scheduler integration.
          apscheduler = pythonPackages.apscheduler.overridePythonAttrs (_: { doCheck = false; });
          requests-ratelimiter = pythonPackages.requests-ratelimiter;
          # Wantlist invokes beets' core commands directly. Build that core rather than the
          # nixpkgs convenience package, which bundles optional plugins and GStreamer support
          # into a multi-gigabyte desktop/media runtime closure.
          beets = pythonPackages.buildPythonPackage rec {
            pname = "beets";
            version = "2.13.1";
            src = pkgs.fetchFromGitHub {
              owner = "beetbox";
              repo = "beets";
              tag = "v${version}";
              hash = "sha256-f25Uv7PRKBFUWah6pvEwwTFjxXKQfmAP2fyTNFJyWB0=";
            };
            pyproject = true;
            build-system = [ pythonPackages.hatchling ];
            dependencies = with pythonPackages; [
              confuse
              jellyfish
              lap
              mediafile
              munkres
              musicbrainzngs
              packaging
              platformdirs
              pyyaml
              requests-ratelimiter
              typing-extensions
              unidecode
            ];
            doCheck = false;
          };

          backend = pythonPackages.buildPythonPackage {
            pname = "wantlist-backend";
            version = "0.1.0";
            src = ./backend;
            pyproject = true;
            build-system = [ pythonPackages.hatchling ];
            dependencies = with pythonPackages; [
              alembic
              apscheduler
              beets
              fastapi
              httpx
              psycopg
              pydantic-settings
              python-multipart
              sqlalchemy
              uvicorn
            ];
            doCheck = false;
          };

          pythonEnv = python.withPackages (_: [ backend ]);
          frontend = pkgs.buildNpmPackage {
            pname = "wantlist-frontend";
            version = "0.1.0";
            src = ./frontend;
            npmDepsHash = "sha256-nQwHvZAByd5Eg7Fe/p8nujBL2AcJnGtYserYw7k3MaE=";
            npmBuildScript = "build";
            installPhase = ''
              runHook preInstall
              mkdir -p "$out"
              cp -r dist/. "$out/"
              runHook postInstall
            '';
          };

          backendSource = pkgs.runCommand "wantlist-backend-source" { src = ./backend; } ''
            cp -R "$src" "$out"
            chmod -R u+w "$out"
          '';

          api = pkgs.writeShellApplication {
            name = "wantlist-api";
            runtimeInputs = [ pkgs.openssh pkgs.rsync ];
            text = ''
              export WANTLIST_STATIC_DIR="''${WANTLIST_STATIC_DIR:-${frontend}}"
              exec ${pythonEnv}/bin/python -m uvicorn wantlist.app:app \
                --host "''${WANTLIST_HOST:-127.0.0.1}" \
                --port "''${WANTLIST_PORT:-8000}" \
                "$@"
            '';
          };

          worker = pkgs.writeShellApplication {
            name = "wantlist-worker";
            runtimeInputs = [ pkgs.openssh pkgs.rsync ];
            text = ''
              exec ${pythonEnv}/bin/python -m wantlist.worker "$@"
            '';
          };

          migrations = pkgs.writeShellApplication {
            name = "wantlist-migrate";
            text = ''
              cd ${backendSource}
              exec ${pythonEnv}/bin/alembic "$@"
            '';
          };
        in
        rec {
          inherit api backend frontend migrations worker;
          wantlist-api = api;
          wantlist-worker = worker;
          wantlist-migrate = migrations;
          image = pkgs.dockerTools.buildLayeredImage {
            name = "wantlist";
            tag = "latest";
            contents = [ api worker migrations ];
            config = {
              Cmd = [ "${api}/bin/wantlist-api" ];
              ExposedPorts = { "8000/tcp" = { }; };
            };
          };
          default = api;
        });
    };
}
