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

## Building for Production

```bash
cd streamlit_app
pip install -r requirements.txt
streamlit run app.py --logger.level=error
```

For deploying Streamlit, see [Streamlit Cloud Deployment](https://docs.streamlit.io/streamlit-community-cloud/deploy-your-app)

## API Endpoints

The stock scanner uses external APIs:
- **IBKR** - Real-time price, volume, short interest, shortable shares
- **Finnhub** - Company news and fundamentals
- **Alpha Vantage** - News sentiment analysis
- **Benzinga** - Premium news (optional)

## Technologies Used

- **Streamlit 1.28.0** - Web app framework
- **ib_insync 10.19.0** - Interactive Brokers API
- **Finnhub Python Client** - News & company data
- **Alpha Vantage** - News sentiment
- **Benzinga API** - Premium news (optional)
- **Plotly** - Interactive charts
- **Pandas** - Data manipulation

## Environment Variables

See [streamlit_app/.env.example](streamlit_app/.env.example) for all configuration options:
```
IBKR_HOST=127.0.0.1
IBKR_PORT=7497
IBKR_CLIENT_ID=1
FINNHUB_API_KEY=your_key
ALPHA_VANTAGE_KEY=your_key
BENZINGA_API_KEY=your_key (optional)
```

## Contributing

1. Create a feature branch
2. Make your changes
3. Test thoroughly
4. Submit a pull request

## License

MIT
