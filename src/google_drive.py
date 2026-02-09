"""Google Drive API integration for reading tax documents."""

import os
import io
import tempfile
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload


# Scopes required for reading files from Google Drive
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

# Supported file MIME types for tax documents
SUPPORTED_MIME_TYPES = {
    'application/pdf': '.pdf',
    'image/jpeg': '.jpg',
    'image/png': '.png',
    'image/tiff': '.tiff',
    'text/csv': '.csv',
    'application/vnd.ms-excel': '.xls',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx',
}


class GoogleDriveClient:
    """Client for interacting with Google Drive API."""

    def __init__(self, credentials_path: str = 'config/credentials.json',
                 token_path: str = 'config/token.json'):
        """
        Initialize the Google Drive client.

        Args:
            credentials_path: Path to the OAuth2 credentials JSON file
            token_path: Path to store the access token
        """
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.service = None
        self._authenticate()

    def _authenticate(self) -> None:
        """Authenticate with Google Drive API using OAuth2."""
        creds = None

        # Load existing token if available
        if os.path.exists(self.token_path):
            creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)

        # If no valid credentials, go through OAuth flow
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(self.credentials_path):
                    raise FileNotFoundError(
                        f"Credentials file not found at {self.credentials_path}. "
                        "Please download your OAuth2 credentials from Google Cloud Console."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_path, SCOPES
                )
                creds = flow.run_local_server(port=0)

            # Save credentials for future use
            os.makedirs(os.path.dirname(self.token_path), exist_ok=True)
            with open(self.token_path, 'w') as token:
                token.write(creds.to_json())

        self.service = build('drive', 'v3', credentials=creds)

    def list_files(self, folder_id: Optional[str] = None,
                   mime_types: Optional[list] = None) -> list:
        """
        List files in Google Drive, optionally filtered by folder and MIME type.

        Args:
            folder_id: ID of the folder to list files from (None for root)
            mime_types: List of MIME types to filter by

        Returns:
            List of file metadata dictionaries
        """
        query_parts = []

        # Filter by folder
        if folder_id:
            query_parts.append(f"'{folder_id}' in parents")

        # Filter by MIME types
        if mime_types:
            mime_conditions = [f"mimeType='{mt}'" for mt in mime_types]
            query_parts.append(f"({' or '.join(mime_conditions)})")

        # Exclude trashed files
        query_parts.append("trashed=false")

        query = ' and '.join(query_parts)

        results = self.service.files().list(
            q=query,
            pageSize=100,
            fields="nextPageToken, files(id, name, mimeType, size, modifiedTime)"
        ).execute()

        return results.get('files', [])

    def list_tax_documents(self, folder_id: Optional[str] = None) -> list:
        """
        List tax-related documents (PDFs, images, spreadsheets) in a folder.

        Args:
            folder_id: ID of the folder containing tax documents

        Returns:
            List of tax document metadata
        """
        return self.list_files(
            folder_id=folder_id,
            mime_types=list(SUPPORTED_MIME_TYPES.keys())
        )

    def download_file(self, file_id: str, destination: Optional[str] = None) -> str:
        """
        Download a file from Google Drive.

        Args:
            file_id: ID of the file to download
            destination: Local path to save the file (auto-generated if None)

        Returns:
            Path to the downloaded file
        """
        # Get file metadata
        file_metadata = self.service.files().get(fileId=file_id).execute()
        file_name = file_metadata.get('name', 'unnamed')
        mime_type = file_metadata.get('mimeType', '')

        # Determine file extension
        extension = SUPPORTED_MIME_TYPES.get(mime_type, '')
        if not extension and '.' in file_name:
            extension = '.' + file_name.split('.')[-1]

        # Create destination path
        if destination is None:
            temp_dir = tempfile.mkdtemp(prefix='tax_docs_')
            destination = os.path.join(temp_dir, f"{file_name}")

        # Download file
        request = self.service.files().get_media(fileId=file_id)
        with io.FileIO(destination, 'wb') as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()

        return destination

    def download_all_tax_documents(self, folder_id: Optional[str] = None,
                                    destination_dir: Optional[str] = None) -> list:
        """
        Download all tax documents from a folder.

        Args:
            folder_id: ID of the folder containing tax documents
            destination_dir: Directory to save downloaded files

        Returns:
            List of paths to downloaded files
        """
        if destination_dir is None:
            destination_dir = tempfile.mkdtemp(prefix='tax_docs_')
        else:
            os.makedirs(destination_dir, exist_ok=True)

        documents = self.list_tax_documents(folder_id)
        downloaded_files = []

        for doc in documents:
            file_path = os.path.join(destination_dir, doc['name'])
            self.download_file(doc['id'], file_path)
            downloaded_files.append({
                'path': file_path,
                'name': doc['name'],
                'mime_type': doc['mimeType'],
                'id': doc['id']
            })
            print(f"Downloaded: {doc['name']}")

        return downloaded_files

    def get_folder_id_by_name(self, folder_name: str,
                               parent_id: Optional[str] = None) -> Optional[str]:
        """
        Find a folder ID by its name.

        Args:
            folder_name: Name of the folder to find
            parent_id: ID of the parent folder to search in

        Returns:
            Folder ID if found, None otherwise
        """
        query_parts = [
            f"name='{folder_name}'",
            "mimeType='application/vnd.google-apps.folder'",
            "trashed=false"
        ]

        if parent_id:
            query_parts.append(f"'{parent_id}' in parents")

        query = ' and '.join(query_parts)

        results = self.service.files().list(
            q=query,
            pageSize=1,
            fields="files(id, name)"
        ).execute()

        files = results.get('files', [])
        return files[0]['id'] if files else None
