"""
Capítulos do vídeo (o que o yt-dlp já trouxe) como lista de faixas com
início, fim e duração. Só vale com 5+ capítulos de título não vazio: menos
que isso raramente é uma tracklist.
"""
from typing import List, Dict, Optional

class YouTubeChaptersExtractor:
    """Extrai tracklist dos chapters do YouTube"""
    
    @staticmethod
    def extract_from_video_info(video_info: dict) -> Optional[List[Dict]]:
        """
        Extrai chapters do dict retornado por yt-dlp
        
        Retorna lista de tracks ou None se não tiver chapters
        """
        chapters = video_info.get('chapters', [])
        
        if not chapters or len(chapters) < 3:
            return None  # Muito poucos chapters, provavelmente não é tracklist
        
        tracks = []
        
        for i, chapter in enumerate(chapters, 1):
            title = chapter.get('title', '').strip()
            start_time = chapter.get('start_time', 0)
            end_time = chapter.get('end_time', 0)
            
            # Valida título (não pode ser muito curto)
            if len(title) < 2:
                continue
            
            # Calcula duração
            duration_seconds = int(end_time - start_time)
            duration_str = YouTubeChaptersExtractor._seconds_to_duration(duration_seconds)
            
            tracks.append({
                'number': i,
                'title': title,
                'start_time': int(start_time),
                'end_time': int(end_time),
                'duration': duration_str,
                'duration_seconds': duration_seconds
            })
        
        # Valida: deve ter pelo menos 5 faixas
        if len(tracks) >= 5:
            return tracks
        
        return None
    
    @staticmethod
    def _seconds_to_duration(seconds: int) -> str:
        """Converte segundos para formato MM:SS"""
        mins = seconds // 60
        secs = seconds % 60
        return f"{mins}:{secs:02d}"
    