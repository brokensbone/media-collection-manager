FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "beets==2.12.0" mediafile typing_extensions

WORKDIR /work
COPY make_fixture.py albums.json ./

ENTRYPOINT ["python", "make_fixture.py"]
