import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

class DatabaseHandler:
    def __init__(self):
        # First connect to postgres to create database if needed
        self.base_conn_params = {
            'dbname': 'omdb',
            'user': 'postgres',
            'password': 'Amanfiy77',
            'host': 'localhost',
            'port': '5432'
        }
        self.create_database()
        
        # Then set connection params for our database
        self.conn_params = {**self.base_conn_params, 'dbname': 'omdb'}
        self.initialize_database()

    def create_database(self):
        try:
            # Connect to default postgres database
            with psycopg2.connect(**self.base_conn_params) as conn:
                conn.autocommit = True
                with conn.cursor() as cur:
                    # Check if database exists
                    cur.execute("SELECT 1 FROM pg_database WHERE datname = 'omdb'")
                    if not cur.fetchone():
                        # Create database if it doesn't exist
                        cur.execute("CREATE DATABASE omdb")
        except Exception as e:
            print(f"Error creating database: {e}")

    def get_connection(self):
        return psycopg2.connect(**self.conn_params, cursor_factory=RealDictCursor)

    def initialize_database(self):
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # First create movies table with telegram_file_id
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS movies (
                        imdb_id VARCHAR(20) PRIMARY KEY,
                        title TEXT NOT NULL,
                        year VARCHAR(10),
                        poster_url TEXT,
                        plot TEXT,
                        rating VARCHAR(10),
                        telegram_file_id TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                conn.commit()

                # Then create posts table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS posts (
                        id SERIAL PRIMARY KEY,
                        imdb_id VARCHAR(20) REFERENCES movies(imdb_id),
                        message_text TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                conn.commit()

                # Finally create buttons table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS buttons (
                        id SERIAL PRIMARY KEY,
                        post_id INTEGER REFERENCES posts(id),
                        button_text TEXT NOT NULL,
                        button_url TEXT NOT NULL,
                        button_order INTEGER,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                conn.commit()

                # Add tokens table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS tokens (
                        token VARCHAR(64) PRIMARY KEY,
                        download_url TEXT NOT NULL,
                        video_name TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        used_at TIMESTAMP,
                        is_valid BOOLEAN DEFAULT TRUE
                    );
                """)
                conn.commit()

    def check_tables(self):
        """Check if all required tables exist"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public'
                    AND table_name IN ('movies', 'posts', 'buttons');
                """)
                existing_tables = [row['table_name'] for row in cur.fetchall()]
                return {
                    'movies': 'movies' in existing_tables,
                    'posts': 'posts' in existing_tables,
                    'buttons': 'buttons' in existing_tables
                }

    def save_movie(self, movie_info: dict):
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO movies (imdb_id, title, year, poster_url, plot, rating, telegram_file_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (imdb_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    year = EXCLUDED.year,
                    poster_url = EXCLUDED.poster_url,
                    plot = EXCLUDED.plot,
                    rating = EXCLUDED.rating,
                    telegram_file_id = EXCLUDED.telegram_file_id
                    RETURNING imdb_id
                """, (
                    movie_info.get('imdbID'),
                    movie_info.get('Title'),
                    movie_info.get('Year'),
                    movie_info.get('Poster'),
                    movie_info.get('Plot'),
                    movie_info.get('imdbRating'),
                    movie_info.get('telegram_file_id')  # Add this field
                ))
                return cur.fetchone()['imdb_id']

    def create_post(self, imdb_id: str, message_text: str):
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO posts (imdb_id, message_text)
                    VALUES (%s, %s)
                    RETURNING id
                """, (imdb_id, message_text))
                return cur.fetchone()['id']

    def save_buttons(self, post_id: int, buttons: list):
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                for idx, button in enumerate(buttons):
                    cur.execute("""
                        INSERT INTO buttons (post_id, button_text, button_url, button_order)
                        VALUES (%s, %s, %s, %s)
                    """, (post_id, button[0].text, button[0].url, idx))
                conn.commit()

    def get_post(self, post_id: int):
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT p.*, m.*, 
                           json_agg(json_build_object(
                               'text', b.button_text, 
                               'url', b.button_url, 
                               'order', b.button_order
                           )) as buttons
                    FROM posts p
                    JOIN movies m ON p.imdb_id = m.imdb_id
                    LEFT JOIN buttons b ON b.post_id = p.id
                    WHERE p.id = %s
                    GROUP BY p.id, m.imdb_id
                """, (post_id,))
                return cur.fetchone()

    def get_user_posts(self, imdb_id: str):
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT p.id, p.message_text, p.created_at,
                           json_agg(json_build_object(
                               'text', b.button_text,
                               'url', b.button_url,
                               'order', b.button_order
                           )) as buttons
                    FROM posts p
                    LEFT JOIN buttons b ON b.post_id = p.id
                    WHERE p.imdb_id = %s
                    GROUP BY p.id
                    ORDER BY p.created_at DESC
                """, (imdb_id,))
                return cur.fetchall()

    def search_movies(self, query: str, limit: int = 10):
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                search_pattern = f'%{query}%'
                cur.execute("""
                    WITH latest_post AS (
                        SELECT DISTINCT ON (p.imdb_id) 
                            p.id as post_id,
                            p.imdb_id,
                            p.message_text,
                            p.created_at
                        FROM posts p
                        ORDER BY p.imdb_id, p.created_at DESC
                    )
                    SELECT 
                        m.*,
                        lp.message_text as post_text,
                        lp.post_id,
                        m.telegram_file_id,
                        COALESCE(
                            (
                                SELECT json_agg(
                                    json_build_object(
                                        'text', b.button_text,
                                        'url', b.button_url
                                    )
                                )
                                FROM buttons b
                                WHERE b.post_id = lp.post_id
                            ),
                            '[]'::json
                        ) as latest_buttons
                    FROM movies m
                    LEFT JOIN latest_post lp ON m.imdb_id = lp.imdb_id
                    WHERE LOWER(m.title) LIKE LOWER(%(pattern)s)
                    OR m.imdb_id LIKE 'manual_%%'
                    ORDER BY 
                        CASE WHEN m.imdb_id LIKE 'manual_%%' THEN 1 ELSE 0 END,
                        m.created_at DESC
                    LIMIT %(limit)s
                """, {'pattern': search_pattern, 'limit': limit})
                return cur.fetchall()

    def save_token(self, token: str, download_url: str, video_name: str):
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO tokens (token, download_url, video_name)
                    VALUES (%s, %s, %s)
                    RETURNING token
                """, (token, download_url, video_name))
                return cur.fetchone()['token']

    def verify_token(self, token: str) -> dict:
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT * FROM tokens
                    WHERE token = %s AND is_valid = TRUE
                    AND (used_at IS NULL OR used_at > NOW() - INTERVAL '24 hours')
                """, (token,))
                return cur.fetchone()

    def mark_token_used(self, token: str):
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE tokens
                    SET used_at = NOW()
                    WHERE token = %s
                """, (token,))
                conn.commit()
