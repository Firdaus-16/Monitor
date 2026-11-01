# Enterprise SD-WAN Monitoring System for Bank Kalsel

A comprehensive SD-WAN monitoring system designed for Bank Kalsel with 67 branches across dual-provider infrastructure (Lintasarta/Versa & ICON/Starlink).

## Features

- **Dual-Provider Monitoring**: Supports both Lintasarta/Versa and ICON/Starlink providers
- **Excel Bulk Import**: Automated branch data import from Excel files
- **Real-time Monitoring**: Track router status, latency, and downtime
- **Web Dashboard**: Responsive web interface for monitoring
- **Database Persistence**: SQLite database with comprehensive schema
- **Docker Containerization**: Easy deployment with Docker

## Project Structure

```
bank-kalsel-sdwan-monitoring/
├── app.py                 # Main Flask application
├── database.py            # Database management module
├── importer.py            # Excel import functionality
├── requirements.txt       # Python dependencies
├── Dockerfile            # Docker container configuration
├── docker-compose.yml    # Docker orchestration
├── templates/            # HTML templates
│   └── index.html        # Main dashboard
├── data/                 # Database storage
├── reports/              # Report storage
└── uploads/              # Upload directory
```

## Database Schema

The system uses SQLite with the following tables:

- **users**: User authentication and authorization
- **routers**: SD-WAN router information and configuration
- **downtime_history**: Incident tracking and downtime records
- **latency_history**: Performance monitoring data
- **runtime_states**: Real-time router status
- **settings**: Application configuration

## Setup & Installation

### Using Docker (Recommended)

1. Build and start the containers:
   ```bash
   docker-compose up -d
   ```

2. Access the web interface:
   - http://localhost:5000

### Manual Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Initialize the database:
   ```bash
   python database.py
   ```

3. Start the application:
   ```bash
   python app.py
   ```

## Default Credentials

- **Username**: admin
- **Password**: admin123

⚠️ **Important**: Change the default password in production!

## Excel Import Format

The Excel file should contain the following columns:
- Site/Cabang
- IP Lintas
- IP ICON
- Access Type
- Nojar Versa
- Nojar Starlink
- Lat
- Long
- Nama PIC
- No WA PIC
- No WA Provider

## API Endpoints

- `GET /api/routers` - Get all routers
- `GET /api/routers/<ip>` - Get specific router
- `POST /api/routers` - Create new router
- `GET /api/health` - Health check

## Configuration

Application settings can be configured through the `settings` table in the database or by modifying the default values in `database.py`.

## License

Proprietary - Bank Kalsel Internal Use Only