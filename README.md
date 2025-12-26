# Stock Trading Application

A modern full-stack application with a FastAPI Python backend and React frontend.

## Project Structure

```
stock-trading/
├── backend/                         # FastAPI REST API
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                  # FastAPI app entry
│   │   ├── models/                  # Database models
│   │   ├── routes/                  # API endpoints
│   │   ├── schemas/                 # Pydantic schemas
│   │   └── services/                # Business logic
│   ├── tests/
│   ├── config.py
│   ├── requirements.txt
│   └── .env.example
│
├── frontend/                        # React + Vite Frontend
│   ├── src/
│   │   ├── components/              # React components
│   │   ├── pages/
│   │   ├── styles/
│   │   ├── utils/                   # API utilities
│   │   ├── App.jsx
│   │   └── main.jsx
│   ├── public/
│   ├── package.json
│   ├── vite.config.js
│   └── .env.example
│
├── streamlit_app/                   # Streamlit Stock Scanner
│   ├── app.py                       # Main scanner app
│   ├── requirements.txt
│   ├── .env.example
│   ├── .streamlit/
│   │   └── config.toml
│   └── README.md
│
├── .gitignore
└── README.md
```

## Development

### Running All Three Services

You can run all three services simultaneously in separate terminals:

**Terminal 1 - FastAPI Backend** (port 8000):
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app/main.py
```

**Terminal 2 - React Frontend** (port 3000/5173):
```bash
cd frontend
npm install
npm run dev
```

**Terminal 3 - Streamlit Stock Scanner** (port 8501):
```bash
cd streamlit_app
pip install -r requirements.txt
# Setup .env file with API keys (see streamlit_app/README.md)
streamlit run app.py
```

Access all services:
- 🎨 **Frontend**: `http://localhost:3000` (Vite) or `http://localhost:5173`
- 🔧 **Backend API**: `http://localhost:8000`
- 📊 **Stock Scanner**: `http://localhost:8501`
- 📚 **API Docs**: `http://localhost:8000/docs`

### Backend Only

1. Navigate to the backend directory:
```bash
cd backend
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create a `.env` file from the example:
```bash
cp .env.example .env
```

5. Run the server:
```bash
python app/main.py
```

The backend will be available at `http://localhost:8000`

API documentation: `http://localhost:8000/docs`

### Frontend Only

1. Navigate to the frontend directory:
```bash
cd frontend
```

2. Install dependencies:
```bash
npm install
```

3. Create a `.env` file from the example:
```bash
cp .env.example .env
```

4. Start the development server:
```bash
npm run dev
```

The frontend will be available at `http://localhost:3000` (or `http://localhost:5173` for Vite default)

### Streamlit Stock Scanner

For detailed setup of the Streamlit app, see [streamlit_app/README.md](streamlit_app/README.md)

**Quick Start:**
```bash
cd streamlit_app
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your IBKR connection and API keys
streamlit run app.py
```

**Requirements:**
- Interactive Brokers TWS/Gateway running with Read-Only API enabled
- Free API keys from: Finnhub, Alpha Vantage (optional: Benzinga)

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
