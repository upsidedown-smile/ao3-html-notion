from flask import Flask, request, render_template, jsonify
import os
from dotenv import load_dotenv
from notion_client import Client
from bs4 import BeautifulSoup
import tempfile
import re

load_dotenv()

app = Flask(__name__)
notion = Client(auth=os.getenv("NOTION_TOKEN"))
database_id = os.getenv("NOTION_DATABASE_ID")

upload_history = []

@app.route('/')
def index():
    return render_template('index.html', history=upload_history)

@app.route('/submit', methods=['POST'])
def submit():
    if 'ao3_file' not in request.files:
        return jsonify({"success": False, "error": "No file uploaded."})

    file = request.files['ao3_file']
    if file.filename == '':
        return jsonify({"success": False, "error": "No selected file."})

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.html') as tmp_file:
            file.save(tmp_file.name)
            with open(tmp_file.name, 'r', encoding='utf-8') as f:
                soup = BeautifulSoup(f, 'html.parser')
        os.remove(tmp_file.name)

        # Title
        title_tag = soup.find('h1')
        title = title_tag.get_text(strip=True) if title_tag else None

        # Author
        byline_tag = soup.find('div', class_='byline')
        author = byline_tag.get_text(strip=True).replace('by ', '') if byline_tag else None

        # AO3 URL fallback
        url = request.form.get('ao3_url')
        if not url:
            link_tag = soup.find('p', class_='message')
            url_match = re.search(r'https://archiveofourown\.org/works/\d+', link_tag.get_text()) if link_tag else None
            url = url_match.group(0) if url_match else None

        # Stats
        stats_text = soup.get_text()
        word_match = re.search(r'Words:\s*([\d,]+)', stats_text)
        chapters_match = re.search(r'Chapters:\s*(\d+/\d+)', stats_text)
        words = word_match.group(1) if word_match else None
        chapters = chapters_match.group(1) if chapters_match else None

        # Completion
        status = "Complete" if chapters and chapters.split('/')[0] == chapters.split('/')[1] else "Incomplete"

        # Check fields
        missing = []
        if not title: missing.append("Title")
        if not author: missing.append("Author")
        if not url: missing.append("URL")
        if not words: missing.append("Words")
        if not chapters: missing.append("Chapters")
        if missing:
            raise Exception(f"Missing fields: {', '.join(missing)}")

        from datetime import datetime

        data = {
            "Title": title,
            "Author": author,
            "URL": url,
            "Words": words,
            "Chapters": chapters,
            "Status": status,
            "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M")
        }

        create_notion_page(data)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

def create_notion_page(data):
    upload_history.insert(0, data)
    if len(upload_history) > 5:
        upload_history.pop()

    notion.pages.create(
        parent={"database_id": database_id},
        icon={
            "type": "emoji",
            "emoji": "🐍"
        },
        properties={
            "Title": {"title": [{"text": {"content": data["Title"]}}]},
            "Author": {"rich_text": [{"text": {"content": data["Author"]}}]},
            "AO3 URL": {"url": data["URL"]},
            "Words": {"number": int(data["Words"].replace(',', ''))},
            "Chapters": {"rich_text": [{"text": {"content": data["Chapters"]}}]},
            "Complete": {"checkbox": data["Status"] == "Complete"},
        }
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)), debug=True)
