📈 AI Stock Market Assistant

An AI-powered stock market chatbot built with FastAPI that provides real-time stock information, company fundamentals, market news, and AI-generated investment insights using Large Language Models (LLMs).

🚀 Features

* 🔍 Search stocks by company name or ticker symbol
* 💹 Fetch real-time stock prices and market data
* 📰 Retrieve the latest financial and market news
* 🤖 AI-powered responses using an LLM
* 📊 Company fundamentals and key financial metrics
* ⚡ Fast and lightweight REST API built with FastAPI

⸻

🛠️ Tech Stack

* Backend: FastAPI
* Language: Python
* LLM: Groq (Llama 3.x)
* Stock Data: yfinance
* News API: News Search API
* Environment Management: python-dotenv

⸻

📁 Project Structure

stock-chatbot-backend/
├── main.py
├── search_client.py
├── index.html
├── .gitignore
├── .env.example
└── README.md

⸻

⚙️ Installation

Clone the repository:

git clone https://github.com/<your-username>/stock-chatbot-backend.git
cd stock-chatbot-backend

Create a virtual environment:

python -m venv venv

Activate the virtual environment:

macOS/Linux

source venv/bin/activate

Windows

venv\Scripts\activate

Install dependencies:

pip install -r requirements.txt

⸻

🔑 Environment Variables

Create a key.env (or .env) file in the project root and add your API keys.

Example:

GROQ_API_KEY=your_groq_api_key
NEWS_API_KEY=your_news_api_key

⸻

▶️ Run the Application

uvicorn main:app --reload

The API will be available at:

http://127.0.0.1:8000

Interactive API documentation:

http://127.0.0.1:8000/docs

⸻

Example Queries

* What is the current price of Apple?
* Show me today’s news for Tesla.
* Compare Microsoft and Google stocks.
* Give me the fundamentals of NVIDIA.
* Should I invest in Amazon?

⸻

Future Improvements

* Portfolio tracking
* Watchlist management
* Technical indicator analysis
* Historical price charts
* Authentication and user accounts
* Deployment on Render or Railway

⸻

Disclaimer

This project is intended for educational and demonstration purposes only. It does not constitute financial or investment advice.

⸻

Author

Khushal Taori

If you found this project useful, consider giving it a ⭐ on GitHub.
