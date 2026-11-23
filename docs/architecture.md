# PORTFLOW System Architecture

## Overview

PORTFLOW is a web-based system designed to automate the processing of maritime operational PDF documents and support the generation of standardized email reports.

## Architecture Components

### Frontend

The frontend consists of HTML, CSS and JavaScript, providing the user interface and interaction with the system.

### Backend

The backend is developed using Python and Flask. It manages authentication, operational workflows, API endpoints and the interaction between the frontend and the database.

### Database

SQLite is used for data persistence, storing information related to users, customers, vessels, PDF processing and email reports.

### PDF Processing

The system uses pypdf and custom extraction logic to validate and extract information from operational PDF documents.

## Data Management

The database contains entities associated with users, customers, vessels, PDF processing and email reports.

## System Integration

The frontend communicates with the Flask backend through API endpoints. The backend handles processing, data persistence and operational logic.