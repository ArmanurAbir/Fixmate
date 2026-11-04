# FixMate — Flask REST API Backend

## 1. Project Overview

FixMate is a service management REST API developed using Python, Flask and MongoDB.

The application provides backend functionality for managing customers, service providers, service categories, provider availability, service requests, quotations, bookings, reviews and reports.

The project uses a modular Flask architecture and MongoDB for storing and retrieving application data.

## 2. Technologies Used

- Python
- Flask
- MongoDB
- PyMongo
- Postman
- Visual Studio Code
- RESTful API
- JSON

## 3. Project Structure

The backend is organised into separate Python modules.

```text
Fix_mate/
│
├── app/
│   ├── __init__.py
│   ├── auth.py
│   ├── customer.py
│   ├── providers.py
│   ├── service_categories.py
│   ├── service_request.py
│   ├── quotations.py
│   ├── avalability.py
│   ├── bookings.py
│   ├── reviews.py
│   └── reports.py
│
├── run.py
└── .env
```

The application uses Flask Blueprints to separate API functionality into different modules.

## 4. Database

Database: `fixmate`

Database Management System: MongoDB

The application uses PyMongo to communicate with MongoDB.

Database configuration is managed using environment variables:

```env
MONGO_URI=mongodb://localhost:27017/
MONGO_DB_NAME=fixmate
```

## 5. Main Features

### Customer Management
- Create customer profiles
- Retrieve customer information
- Update customer details
- Delete customer records

### Provider Management
- Retrieve service providers
- Create provider records
- Update provider information
- Delete provider records

### Authentication
- Customer authentication
- Provider authentication
- HTTP Basic Authentication
- Protected API endpoints

### Service Management
- Retrieve service categories
- Retrieve service details
- Manage provider availability

### Service Requests
- Create service requests
- Retrieve service requests
- Update service requests
- Delete service requests

### Quotations
- Submit quotations
- Retrieve quotations
- Update eligible quotations
- Accept quotations
- Manage quotation status

### Bookings
- Create bookings through the quotation acceptance workflow
- Retrieve bookings
- Update booking details
- Manage booking status
- Maintain booking status history

### Reviews
- Create booking reviews
- Retrieve booking reviews
- Update reviews
- Delete reviews
- Retrieve provider reviews

### Reports
- Provider performance
- Monthly revenue
- Service demand
- Cancellations

## 6. Running the Application

### Step 1 — Install Python

Ensure Python is installed on the computer.

### Step 2 — Install Dependencies

Install the required Python packages for the project.

```bash
pip install flask pymongo python-dotenv
```

Additional dependencies may be required depending on the final project configuration.

### Step 3 — Start MongoDB

Ensure the local MongoDB server is running.

### Step 4 — Configure Environment Variables

Create or configure the `.env` file with the appropriate MongoDB connection details.

### Step 5 — Run Flask

Open the terminal in the project directory and execute:

```bash
python run.py
```

The application runs locally at:

```text
http://127.0.0.1:5050
```

## 7. API Endpoints

The REST API uses the following versioned prefix:

```text
/api/v1.0/
```

Main API resource groups include:

| Resource | API Prefix |
|---|---|
| Authentication | `/api/v1.0/auth` |
| Customers | `/api/v1.0/customers` |
| Providers | `/api/v1.0/providers` |
| Services | `/api/v1.0/services` |
| Service Requests | `/api/v1.0/requests` |
| Quotations | `/api/v1.0/requests` |
| Bookings | `/api/v1.0/bookings` |

Availability and provider reviews are accessed through provider-related routes. Booking reviews are accessed through booking-related routes.

The exact HTTP methods and individual routes are documented in the Postman collection.

## 8. API Testing Using Postman

Postman was used to test the REST API endpoints.

Postman Collection Name: **FixMate API Docs**

Testing covered:

- GET requests
- POST requests
- PATCH requests
- DELETE requests
- Authentication
- JSON responses
- CRUD operations
- Quotation workflows
- Booking status changes
- Review management
- Reporting endpoints

### Automated Postman Test Results

| Test Metric | Result |
|---|---|
| Passed Assertions | 48 |
| Failed Assertions | 0 |
| Test Errors | 0 |
| Collection Iterations | 1 |

All 48 automated assertions passed during the recorded collection run.

Some requests returned HTTP 401 or 409 responses because of authentication restrictions, existing resources or application business rules. These responses should be evaluated separately from the automated assertion results.

## 9. HTTP Response Codes

The API uses HTTP status codes to communicate request results.

| Status Code | Meaning |
|---|---|
| 200 | OK |
| 201 | Created |
| 400 | Bad Request |
| 401 | Unauthorized |
| 404 | Not Found |
| 409 | Conflict |

## 10. Backend Architecture

The FixMate backend uses a modular application structure.

Flask handles incoming HTTP requests, processes API operations and returns JSON responses.

PyMongo provides communication between Flask and MongoDB.

Flask Blueprints separate different resources into independent modules, making the backend easier to organise, test and maintain.

## 11. Security and Validation

The application includes authentication checks for protected API endpoints.

Customer and provider operations use authentication and access restrictions.

The API also applies business rules to certain operations, including quotation updates and booking status transitions.

Environment variables are used for database configuration. Sensitive credentials should not be committed to public repositories.

## 12. Testing Evidence

The project was tested using Postman.

Testing evidence includes:

- API request and response results
- HTTP status codes
- Automated Postman test results
- Successful CRUD operations
- Authentication testing
- Booking and quotation workflow testing
- Review and reporting endpoint testing

## 13. Conclusion

FixMate demonstrates the development of a RESTful backend application using Python, Flask and MongoDB.

The project provides API functionality for customer management, service providers, availability, service requests, quotations, bookings, reviews and reporting.

The backend was tested manually and through automated Postman assertions, with 48 assertions passing in the recorded collection run.

The project demonstrates REST API development, NoSQL database integration, modular backend architecture, authentication, CRUD operations and API testing.