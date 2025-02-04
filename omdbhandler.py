import requests

class OMDBHandler:
    def __init__(self, api_key='213c43fa'):
        self.api_key = api_key
        self.base_url = 'https://www.omdbapi.com/'

    def get_movie_info(self, movie_name: str) -> list:
        api_url = f'{self.base_url}?s={movie_name}&apikey={self.api_key}'
        response = requests.get(api_url)
        return response.json().get('Search', [])

    def get_movie_details(self, imdb_id: str) -> dict:
        api_url = f'{self.base_url}?i={imdb_id}&apikey={self.api_key}'
        response = requests.get(api_url)
        return response.json()

    def format_movie_message(self, movie_info: dict) -> tuple:
        if movie_info['Response'] != 'True':
            return None, None

        imdb_id = movie_info.get('imdbID', '')
        imdb_link = f'https://www.imdb.com/title/{imdb_id}/'
        poster = movie_info.get('Poster', 'N/A')

        message_text = (
            f"**Movie**: [{movie_info['Title']}]({imdb_link}) ({movie_info.get('Year', 'N/A')})\n"
            f"**Also Known As**: {movie_info['Title']}\n"
            f"**Rating ⭐️**: {movie_info.get('imdbRating', 'N/A')} / 10\n"
            f"**Runtime**: {movie_info.get('Runtime', 'N/A')}\n"
            f"**Release Info**: {movie_info.get('Released', 'N/A')} ([details]({imdb_link}/releaseinfo))\n"
            f"**Genre**: {movie_info.get('Genre', 'N/A')}\n"
            f"**Language**: {movie_info.get('Language', 'N/A')}\n"
            f"**Country of Origin**: {movie_info.get('Country', 'N/A')}\n"
            f"**Story Line**: {movie_info.get('Plot', 'N/A')}\n"
            f"**Directors**: {movie_info.get('Director', 'N/A')}\n"
            f"**Writers**: {movie_info.get('Writer', 'N/A')}\n"
            f"**Stars**: {movie_info.get('Actors', 'N/A')}\n"
            f"[Poster Image]({poster})"
        )

        return message_text, poster