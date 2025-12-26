# Stock Discovery & Scanner App

A real-time stock discovery application using Streamlit with Interactive Brokers, Finnhub, Alpha Vantage, and Benzinga APIs.

## Project Structure

```
stock-trading/
├── streamlit_app/                   # Stock Scanner Application
│   ├── app.py                       # Main Streamlit app
│   ├── requirements.txt             # Dependencies
│   ├── .env.example                 # API keys template
│   ├── .streamlit/
│   │   └── config.toml
│   └── README.md
│
├── .gitignore
└── README.md
```

## Development

### Running the Stock Scanner

```bash
cd streamlit_app
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys and IBKR configuration
streamlit run app.py
```

The app will open at `http://localhost:8501`

### Building for Production

Backend:
```bash
cd backend
pip install -r requirements.txt
# Deploy using gunicorn or similar
```

Frontend:
```bash
cd frontend
npm run build
# Serves static files from dist/ directory
```

## API Endpoints

- `GET /` - Welcome message
- `GET /health` - Health check
- `GET /docs` - Swagger UI documentation
- `GET /redoc` - ReDoc documentation

## Technologies Used

### Backend
- FastAPI 0.109.0
- Uvicorn 0.27.0
- SQLAlchemy 2.0.23
- Pydantic 2.5.0

### Frontend
- React 18.2.0
- Vite 5.0.2
- Axios 1.6.2

### Stock Scanner (Streamlit)
- Streamlit 1.28.0
- ib_insync 10.19.0 (Interactive Brokers)
- Finnhub Python Client (News & Company Data)
- Alpha Vantage (News Sentiment)
- Benzinga API (Premium News - Optional)
- Plotly (Charts)

## Environment Variables

### Backend (.env)
```
DEBUG=True
APP_NAME="Stock Trading API"
DATABASE_URL=sqlite:///./test.db
```

### Frontend (.env)
```
VITE_API_URL=http://localhost:8000
```

## Contributing

1. Create a feature branch
2. Make your changes
3. Test thoroughly
4. Submit a pull request

## License

MIT
