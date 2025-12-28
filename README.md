# Introduction
A Docker container that automatically downloads and converts your Audible audiobooks from AAX/AAXC to M4B format.

The program includes a **web UI** for managing your audiobook library and triggering downloads, plus automatic background syncing every 6 hours.

Audiobooks can be either just their file or ordered directly into folders. This can be beneficial for large libraries or usage with other programs.
The directory structure uses the [audiobookshelf](https://www.audiobookshelf.org/docs#book-directory-structure) convention.
Author/Series/audiobook.m4b or Author/audiobook.m4b if a Series doesn't exist.

## Features

- **Web UI** for viewing and managing your audiobook library
- View all audiobooks with filtering by download status and search
- Edit audiobook metadata (title, author, series, narrators, etc.)
- Trigger downloads for one or more books
- Reset download status to re-download books
- Automatic background sync every 6 hours
- Automatic conversion from AAX/AAXC to M4B format

# Run Image

## Build from source

Run in the Directory with the Dockerfile.
```
docker build -t audible-downloader .
```

List all images.
```
docker images ls
```

replace the container id with your image hash

```
docker run -d \
	--name=audiobookDownloader \
	-e AUDIOBOOK_FOLDERS='True' \
	-p 5000:5000 \
	-v /path/to/audiobookDownloader/config:/config \
	-v /path/to/audiobookDownloader/audiobooks:/audiobooks \
	container id
```

The web UI will be available at `http://localhost:5000`

## First time running
Run the container by one of the given methods.

List all running containers:

`docker ps`

Use the container shell:

`docker exec -it`

write:

`audible quickstart`

and answer the prompts.
The name of the auth file name doesn't matter but it can't be encrypted.
Login over the browser and copy the new URL back into the console after completing the captcha

## Using Docker Compose (Recommended)

The easiest way to run the container:

```bash
docker-compose up -d
```

This will build the image and start the container with the web UI available at `http://localhost:5000`

To stop:
```bash
docker-compose down
```

## Build it yourself
`docker build -t audibleDownloader:1.0 .`

## Using the Web UI

Once the container is running, navigate to `http://localhost:5000` in your web browser.

From the web UI you can:
- View all your audiobooks with search and filtering
- See download status (Downloaded/Pending)
- Edit audiobook metadata
- Trigger downloads for selected books
- Refresh your library from Audible
- Reset download status to re-download books
