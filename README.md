# Introduction
A Docker container that automatically downloads and converts your Audible audiobooks from AAX/AAXC to M4B format.

The program includes a **web UI** for managing your audiobook library and triggering downloads, plus automatic background syncing every 6 hours.

Audiobooks can be either just their file or ordered directly into folders. This can be beneficial for large libraries or usage with other programs.
The directory structure uses the [audiobookshelf](https://www.audiobookshelf.org/docs#book-directory-structure) convention.
Author/Series/audiobook.m4b or Author/audiobook.m4b if a Series doesn't exist.

## Features

- **Web UI** for viewing and managing your audiobook library
- **Real-time download status** with live progress tracking
- **Smart status management** with three states: Downloaded, Pending, and Skipped
- **Skip existing books on startup** to avoid downloading your entire library on first run
- View all audiobooks with filtering by download status and search
- Edit audiobook metadata (title, author, series, narrators, etc.)
- Download all pending books with a single click
- Mark individual books as pending to download them
- Reset download status to re-download books
- Automatic background sync every 6 hours
- Automatic conversion from AAX/AAXC to M4B format
- Visual progress indicators showing current book being downloaded

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
	-e SKIP_EXISTING_ON_STARTUP='False' \
	-e AUDIOBOOK_PROCESSING_DIR='/processing' \
	-e AUDIOBOOK_DESTINATION_DIR='/audiobooks' \
	-p 5000:5000 \
	-v /path/to/config:/config \
	-v /path/to/local/processing:/processing \
	-v /path/to/nas/audiobooks:/audiobooks \
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
- See download status (Downloaded/Pending/Skipped)
- **Monitor real-time download progress** with live status banner
- See which book is currently being downloaded
- Track progress with visual progress bar (e.g., "3 of 10 completed")
- Edit audiobook metadata
- Download all pending books with one click
- Mark individual skipped books as pending to download them
- Refresh your library from Audible
- Reset download status to re-download books

### Real-Time Status Tracking

When downloads or library refreshes are in progress, a status banner appears at the top of the page showing:
- Current operation (Downloading/Refreshing)
- The book currently being processed
- Progress bar with completion count
- Automatic page refresh when operations complete

### Book Status Management

The application uses three status levels:
- **Downloaded (1)**: Book has been successfully downloaded and converted
- **Pending (0)**: Book is queued for download
- **Skipped (-1)**: Book is in your library but marked to skip downloading

### Environment Variables

- `AUDIOBOOK_FOLDERS`: Set to `True` to organize audiobooks into folders following the AudiobookShelf convention (default: False)
- `SKIP_EXISTING_ON_STARTUP`: Set to `True` to mark all pending books as "skipped" on first startup. This is useful when you have a large existing library and only want to download new books going forward. (default: False)
- `AUDIOBOOK_PROCESSING_DIR`: Directory for temporary processing and conversion. Should be fast local storage like an SSD (default: /processing)
- `AUDIOBOOK_DESTINATION_DIR`: Final destination directory where completed audiobooks are moved. Can be a NAS mount (default: /audiobooks)

### Processing vs Destination Directories

The application uses a two-stage approach for optimal performance:

1. **Processing Directory** (`AUDIOBOOK_PROCESSING_DIR`):
   - Files are downloaded to `/app` (in-container)
   - Conversion from AAX/AAXC to M4B happens here
   - Should be mounted to fast local storage (SSD) for best performance
   - Example: `-v /local/ssd/processing:/processing`

2. **Destination Directory** (`AUDIOBOOK_DESTINATION_DIR`):
   - Completed M4B files are moved here after conversion
   - Can be slow network storage like a NAS
   - Example: `-v /mnt/nas/audiobooks:/audiobooks`

This approach ensures fast conversion on local storage, then transfers the finished file to your final destination (which might be slower network storage).
