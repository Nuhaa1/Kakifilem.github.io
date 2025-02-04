from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import Application, CommandHandler, CallbackContext, CallbackQueryHandler, MessageHandler, filters, InlineQueryHandler
import logging
from omdbhandler import OMDBHandler
from datetime import datetime  # Change this line
import json
from database import DatabaseHandler
import re  # Add this import at the top
import secrets
import urllib.parse

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',  # Fix typos in format string
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = '7667495956:AAFO7BdGVFeaYqBa-FNnFSCYhK7FzQPqwKg'
COUNTDOWN_URL = "https://bigdaddyaman.github.io/countdown.html"  # Updated domain
omdb = OMDBHandler()

# Store temporary data
user_data = {}
db = DatabaseHandler()

async def start(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text('Hi! I can share movie information. Use /movie <movie_name> to get started.')

async def movie(update: Update, context: CallbackContext) -> None:
    movie_name = ' '.join(context.args)
    movies = omdb.get_movie_info(movie_name)
    
    if movies:
        buttons = [[InlineKeyboardButton(f"{movie['Title']} ({movie['Year']})", 
                                       callback_data=f"select_{movie['imdbID']}")] 
                  for movie in movies]
        reply_markup = InlineKeyboardMarkup(buttons)
        await update.message.reply_text('Select a movie:', reply_markup=reply_markup)
    else:
        await update.message.reply_text('Movie not found!')

async def manual(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    user_data[user_id] = {
        'mode': 'manual_name',
        'manual_data': {
            'title': None,
            'description': None,
            'photo': None,
            'year': str(datetime.now().year)  # Add str() here
        }
    }
    await update.message.reply_text(
        'First, send me the movie name.\n'
        'Example: Munafik 2'
    )

async def button_handler(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    
    data = query.data.split('_')
    command = data[0]

    # Initialize user data if not exists
    if query.from_user.id not in user_data:
        user_data[query.from_user.id] = {
            'imdb_id': None,
            'movie_info': None,
            'mode': None,
            'buttons': []
        }

    if command == 'select':
        imdb_id = data[1]
        movie_info = omdb.get_movie_details(imdb_id)
        message_text, poster = omdb.format_movie_message(movie_info)
        
        if message_text:
            # Update user data
            user_data[query.from_user.id].update({
                'imdb_id': imdb_id,
                'movie_info': movie_info,
                'mode': None,
                'buttons': []
            })
            
            buttons = [
                [InlineKeyboardButton("Single Download", callback_data=f"single_{imdb_id}")],
                [InlineKeyboardButton("Custom Buttons", callback_data=f"custom_{imdb_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(buttons)
            
            try:
                await query.message.reply_photo(
                    photo=poster,
                    caption=message_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Error sending message: {e}")
                await query.message.reply_text(
                    text=message_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
    
    elif command == 'single':
        user_data[query.from_user.id]['mode'] = 'single'
        await query.message.reply_text('Please send the download link:')
    
    elif command == 'custom':
        user_data[query.from_user.id].update({
            'mode': 'custom',
            'buttons': []
        })
        await query.message.reply_text(
            'Send your button texts and links, one per line:\n'
            'Format: text link\n'
            'Example:\n'
            'Season 1 https://example.com\n'
            'Season 2 https://example.com\n'
            'Season 3 https://example.com\n'
        )
    
    elif command == 'manual':
        if data[1] == 'single':
            user_data[query.from_user.id].update({
                'mode': 'manual_single',  # Change to manual_single
                'manual_data': user_data[query.from_user.id].get('manual_data')  # Preserve manual data
            })
            await query.message.reply_text('Please send the download link:')
        elif data[1] == 'custom':
            user_data[query.from_user.id]['mode'] = 'manual_buttons'
            await query.message.reply_text(
                'Send your button texts and links, one per line:\n'
                'Format: text link\n'
                'Example:\n'
                'Season 1 https://example.com\n'
                'Season 2 https://example.com\n'
                'Season 3 https://example.com'
            )

async def generate_download_link(video_name: str, download_url: str) -> tuple:
    """Generate token and create countdown link"""
    token = secrets.token_urlsafe(16)
    # Store token and download URL in database
    db.save_token(token, download_url, video_name)  # Add this line to save token
    encoded_token = urllib.parse.quote(token)
    encoded_name = urllib.parse.quote(video_name)
    countdown_link = f"{COUNTDOWN_URL}?token={encoded_token}&videoName={encoded_name}"
    return countdown_link, token

async def handle_links(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    if user_id not in user_data:
        return

    user = user_data[user_id]
    text = update.message.text.strip()

    if user.get('mode') == 'manual_name':
        # Extract year if present in the title
        year_match = re.search(r'(\d{4})', text)
        if year_match:
            year = year_match.group(1)
            title = text.replace(year, '').strip()
            user['manual_data'].update({
                'title': title,
                'year': year
            })
        else:
            user['manual_data']['title'] = text
        
        user['mode'] = 'manual_description'
        await update.message.reply_text(
            f'Title: {user["manual_data"]["title"]}\n'
            f'Year: {user["manual_data"]["year"]}\n\n'
            'Now send me the movie description in any format.'
        )
        return

    elif user.get('mode') == 'manual_description':
        user['manual_data']['description'] = text
        user['mode'] = 'manual_photo'
        await update.message.reply_text('Now send me the movie poster photo.')
        return

    elif user.get('mode') == 'manual_buttons':
        try:
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            buttons = []
            
            for line in lines:
                if ' ' not in line:
                    continue
                    
                button_text, link = line.rsplit(' ', 1)
                button_text = button_text.strip()
                link = link.strip()
                
                if not link.startswith(('http://', 'https://')):
                    continue
                    
                # Generate countdown link for each button
                countdown_link, token = await generate_download_link(button_text, link)
                buttons.append([InlineKeyboardButton(button_text, url=countdown_link)])

            if buttons:
                # Create a movie-like structure for database
                timestamp = int(datetime.now().timestamp())
                manual_movie = {
                    'imdbID': f"manual_{timestamp}",  # Generate unique ID
                    'Title': user['manual_data']['title'],
                    'Year': str(user['manual_data']['year']),
                    'Poster': None,  # Don't use IMDB poster for manual entries
                    'Plot': user['manual_data']['description'],
                    'telegram_file_id': user['manual_data']['photo']  # Add this line
                }

                # Save to database
                imdb_id = db.save_movie(manual_movie)
                post_id = db.create_post(imdb_id, user['manual_data']['description'])
                db.save_buttons(post_id, buttons)

                # Send message
                reply_markup = InlineKeyboardMarkup(buttons)
                try:
                    await update.message.reply_photo(
                        photo=user['manual_data']['photo'],
                        caption=user['manual_data']['description'],
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    logger.error(f"Error sending photo: {e}")
                    await update.message.reply_text(
                        text=user['manual_data']['description'],
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
                finally:
                    del user_data[user_id]
                
        except Exception as e:
            logger.error(f"Error processing links: {e}")
            await update.message.reply_text(
                'Please send your links in the correct format:\n'
                'text link\n'
                'Example:\n'
                'Season 1 https://example.com'
            )

    elif user.get('mode') == 'manual_description':
        user['manual_data']['description'] = text
        user['mode'] = 'manual_photo'
        await update.message.reply_text('Now send me the movie poster photo.')
        return

    elif user.get('mode') == 'manual_buttons':
        try:
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            buttons = []
            
            for line in lines:
                if ' ' not in line:
                    continue
                    
                button_text, link = line.rsplit(' ', 1)
                button_text = button_text.strip()
                link = link.strip()
                
                if not link.startswith(('http://', 'https://')):
                    continue
                    
                buttons.append([InlineKeyboardButton(button_text, url=link)])

            if buttons:
                movie_info = user['manual_data']
                message_text = movie_info['description']
                poster = movie_info['photo']
                reply_markup = InlineKeyboardMarkup(buttons)

                # Save to database
                imdb_id = movie_info.get('imdbID')
                db.save_movie(movie_info)
                post_id = db.create_post(imdb_id, message_text)
                db.save_buttons(post_id, buttons)

                # Send message
                if poster and poster != 'N/A' and poster.startswith('http'):
                    await update.message.reply_photo(
                        photo=poster,
                        caption=message_text,
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
                else:
                    await update.message.reply_text(
                        text=message_text,
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
                del user_data[user_id]
                
        except Exception as e:
            logger.error(f"Error processing links: {e}")
            await update.message.reply_text(
                'Please send your links in the correct format:\n'
                'text link\n'
                'Example:\n'
                'Season 1 https://example.com'
            )
    
    elif user.get('mode') == 'single':
        original_link = text.strip()  # Store original link
        countdown_link, token = await generate_download_link("Download", original_link)  # Pass original link
        buttons = [[InlineKeyboardButton("Download", url=countdown_link)]]
        movie_info = user['movie_info']
        message_text, poster = omdb.format_movie_message(movie_info)
        reply_markup = InlineKeyboardMarkup(buttons)

        try:
            imdb_id = movie_info.get('imdbID')
            db.save_movie(movie_info)
            post_id = db.create_post(imdb_id, message_text)
            db.save_buttons(post_id, buttons)

            if poster and poster != 'N/A' and poster.startswith('http'):
                await update.message.reply_photo(
                    photo=poster,
                    caption=message_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(
                    text=message_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
        finally:
            del user_data[user_id]

    # Add handling for manual_single mode
    elif user.get('mode') == 'manual_single':
        try:
            buttons = [[InlineKeyboardButton("Download", url=text)]]
            timestamp = int(datetime.now().timestamp())
            manual_movie = {
                'imdbID': f"manual_{timestamp}",
                'Title': user['manual_data']['title'],
                'Year': user['manual_data']['year'],
                'Plot': user['manual_data']['description'],
                'telegram_file_id': user['manual_data']['photo'],
                'Poster': None
            }

            # Save to database
            imdb_id = db.save_movie(manual_movie)
            post_id = db.create_post(imdb_id, user['manual_data']['description'])
            db.save_buttons(post_id, buttons)

            reply_markup = InlineKeyboardMarkup(buttons)
            try:
                await update.message.reply_photo(
                    photo=user['manual_data']['photo'],
                    caption=user['manual_data']['description'],
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Error sending manual single photo: {e}")
                await update.message.reply_text(
                    text=user['manual_data']['description'],
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
        finally:
            del user_data[user_id]
        return

async def handle_photo(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    if user_id not in user_data or user_data[user_id].get('mode') != 'manual_photo':
        return

    user = user_data[user_id]
    photo = update.message.photo[-1]  # Get the largest photo size
    
    # Get file from Telegram and store file_id
    file_id = photo.file_id
    user['manual_data']['photo'] = file_id
    user['manual_data']['poster_url'] = file_id  # Store as poster_url for database

    buttons = [
        [InlineKeyboardButton("Single Download", callback_data="manual_single")],
        [InlineKeyboardButton("Custom Buttons", callback_data="manual_custom")]
    ]
    reply_markup = InlineKeyboardMarkup(buttons)
    
    await update.message.reply_text(
        'Photo received! Choose download option:',
        reply_markup=reply_markup
    )

async def inline_query(update: Update, context: CallbackContext) -> None:
    query = update.inline_query.query.strip()
    
    if not query:
        return
    
    try:
        db_movies = db.search_movies(query)
        logger.info(f"Found {len(db_movies)} movies for query: {query}")
        
        results = []
        for movie in db_movies:
            if not movie:
                continue
                
            title = movie.get('title', '')
            year = movie.get('year', '')
            imdb_id = movie.get('imdb_id', '')
            plot = movie.get('plot', '')
            file_id = movie.get('telegram_file_id')
            buttons = movie.get('latest_buttons', []) or []
            
            if not title:
                continue

            # Different message format for manual vs IMDB entries
            is_manual = imdb_id and imdb_id.startswith('manual_')
            if is_manual:
                message_text = (
                    f"**Movie**: {title} ({year})\n"
                    f"**Story Line**: {plot}\n"
                )
            else:
                message_text = (
                    f"**Movie**: [{title}](https://www.imdb.com/title/{imdb_id}/) ({year})\n"
                    f"**Story Line**: {plot}\n\n"
                    f"[More Details](https://www.imdb.com/title/{imdb_id}/)"
                )
            
            if buttons:
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton(btn['text'], url=btn['url'])]
                    for btn in buttons if btn and 'text' in btn and 'url' in btn
                ])
                
                # Set description based on whether we have a file_id
                description = f"{title} - Click to share with download links" if file_id else (plot[:100] + "..." if plot else "Click to share")
                
                result = InlineQueryResultArticle(
                    id=imdb_id or f"manual_{int(datetime.now().timestamp())}",
                    title=f"{title} ({year})",
                    input_message_content=InputTextMessageContent(
                        message_text=message_text,
                        parse_mode='Markdown'
                    ),
                    reply_markup=keyboard,
                    description=description
                )
                
                results.append(result)
        
        if not results:
            results.append(
                InlineQueryResultArticle(
                    id='not_found',
                    title='No results found',
                    input_message_content=InputTextMessageContent(
                        message_text='No movies found for your search.'
                    ),
                    description='Try a different search term'
                )
            )
        
        await update.inline_query.answer(results)
    except Exception as e:
        logger.error(f"Error in inline query: {e}", exc_info=True)
        await update.inline_query.answer([
            InlineQueryResultArticle(
                id='error',
                title='Error occurred',
                input_message_content=InputTextMessageContent(
                    message_text='Sorry, an error occurred while searching. Please try again.'
                ),
                description='Internal error'
            )
        ])

def main():
    application = Application.builder().token(TOKEN).build()

    # Add existing handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("movie", movie))
    application.add_handler(CommandHandler("manual", manual))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_links))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(InlineQueryHandler(inline_query))

    application.run_polling()

    application.add_handler(InlineQueryHandler(inline_query))
if __name__ == '__main__':
    main()


    application.run_polling()

if __name__ == '__main__':
    main()
