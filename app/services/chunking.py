"""Text chunking service"""
from typing import List, Dict
from app.config import settings


class ChunkingService:
    """Service for splitting text into chunks"""

    def __init__(self):
        self.chunk_size = settings.chunk_size
        self.chunk_overlap = settings.chunk_overlap

    def chunk_text(self, text: str) -> List[Dict[str, any]]:
        """
        Split text into overlapping chunks

        Args:
            text: Full text to chunk

        Returns:
            List of chunk dictionaries with index and text
        """
        chunks = []
        text_length = len(text)

        # Handle empty or very short text
        if text_length == 0:
            return []

        if text_length <= self.chunk_size:
            return [{"chunk_index": 0, "text": text}]

        # Create overlapping chunks
        start = 0
        chunk_index = 0

        while start < text_length:
            # Calculate end position
            end = min(start + self.chunk_size, text_length)

            # Extract chunk
            chunk_text = text[start:end]

            # Add to chunks list
            chunks.append({
                "chunk_index": chunk_index,
                "text": chunk_text
            })

            # Move to next chunk with overlap
            # For the last chunk, we don't need overlap
            if end < text_length:
                start = end - self.chunk_overlap
            else:
                break

            chunk_index += 1

        return chunks


# Singleton instance
chunking_service = ChunkingService()