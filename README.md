# 💼 Web-Based Accounting System

<div align="center">

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-2.0+-green.svg)](https://flask.palletsprojects.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Status](https://img.shields.io/badge/Status-Active-brightgreen.svg)]()

*A comprehensive web-based accounting solution for small businesses and personal finance management*

[Features](#-features) • [Installation](#-installation) • [Usage](#-usage) • [Screenshots](#-screenshots) • [Contributing](#-contributing)

</div>

---

## 📖 Overview

The **Web-Based Accounting System** is a modern, responsive financial management application built with Flask. It provides a complete solution for managing accounts, transactions, and generating financial reports. Designed with a clean, professional interface, this system helps users track their finances efficiently with features like GST calculations, multiple report types, and PDF exports.

## ✨ Features

### 🔐 **User Management**
- Secure user registration and authentication
- Password hashing for enhanced security
- User profile management
- Session management

### 🏦 **Account Management**
- Create and manage different account types:
  - 💰 **Assets** - Cash, Bank accounts, Investments
  - 📋 **Liabilities** - Loans, Credit cards, Payables
  - 💵 **Income** - Revenue, Sales, Other income
  - 💸 **Expenses** - Operating costs, Purchases
- Real-time balance tracking
- Account deletion and modification

### 📊 **Transaction Recording**
- Comprehensive transaction entry system
- GST calculation and tracking
- Multiple transaction types support
- Date-based transaction filtering
- Detailed transaction descriptions

### 📈 **Financial Reports**
- **Balance Sheet** - Assets vs Liabilities overview
- **Income Statement** - Profit & Loss analysis
- **Cash Flow Statement** - Cash movement tracking
- **Account Ledger** - Detailed account history
- Date range filtering for all reports

### 🎨 **Modern UI/UX**
- Responsive design for all devices
- Interactive dashboards with charts
- Toast notifications for user feedback
- Mobile-friendly interface

### 📄 **Export & Printing**
- PDF export functionality
- Print-ready report formats
- Dashboard summary exports

## 🛠️ Technology Stack

| Technology | Purpose | Version |
|------------|---------|---------|
| **Python** | Backend Language | 3.8+ |
| **Flask** | Web Framework | 2.0+ |
| **SQLAlchemy** | Database ORM | Latest |
| **SQLite** | Database | Built-in |
| **HTML5** | Frontend Structure | Latest |
| **CSS3** | Styling & Animations | Latest |
| **JavaScript** | Frontend Interactivity | ES6+ |
| **Font Awesome** | Icons | 6.4.0 |
| **Chart.js** | Data Visualization | Latest |

## 🚀 Installation

### Prerequisites
- Python 3.8 or higher
- pip (Python package manager)
- Git

### Step-by-Step Setup

1. **Clone the Repository**
   ```bash
   git clone https://github.com/GarvRandhar/Web-Based-Accounting-System.git
   cd Web-Based-Accounting-System
   ```

2. **Create Virtual Environment**
   ```bash
   python -m venv venv
   
   # On Windows
   venv\Scripts\activate
   
   # On macOS/Linux
   source venv/bin/activate
   ```

3. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Initialize Database**
   ```bash
   python app.py
   ```
   The application will automatically create the SQLite database on first run.

5. **Run the Application**
   ```bash
   python app.py
   ```

6. **Access the Application**
   Open your browser and navigate to: `http://localhost:5000`

## 📱 Usage

### Getting Started

1. **Register Account**: Create a new user account with username, email, and password
2. **Login**: Access your dashboard with your credentials
3. **Setup Accounts**: Create your chart of accounts (Assets, Liabilities, Income, Expenses)
4. **Record Transactions**: Add transactions with GST calculations
5. **Generate Reports**: View financial reports and export to PDF

### Navigation

- **Dashboard**: Overview of financial health with charts
- **Accounts**: Manage your chart of accounts
- **Transactions**: Record and view all financial transactions
- **Reports**: Access Balance Sheet, Income Statement, Cash Flow, and Ledger
- **Profile**: Update user information and settings

## 📸 Screenshots

### 🏠 Dashboard Overview
![Dashboard](https://github.com/user-attachments/assets/0d83b0a7-4ddc-4d24-972d-881629eae94f)
*Modern dashboard with financial overview and quick stats*

### 🏦 Account Management
![Account Management](https://github.com/user-attachments/assets/9c166f78-227f-4be5-a50f-a0f2b6c92e90)
*Intuitive account creation and management interface*

### 📊 Financial Reports
![Balance Sheet](https://github.com/user-attachments/assets/51c17f1b-d72c-4cca-8dd1-7d1385fadead)
*Professional balance sheet with clear asset and liability breakdown*

### 💼 Transaction Recording
![Transactions](https://github.com/user-attachments/assets/ed830313-5983-48b8-82c1-1d78b63d611a)
*Comprehensive transaction entry with GST calculations*

### 📈 Income Statement
![Income Statement](https://github.com/user-attachments/assets/795704ab-e9b7-4f41-81d9-8bb6d89699fb)
*Detailed profit and loss analysis*

### 🔍 Account Ledger
![Ledger](https://github.com/user-attachments/assets/3504580f-defc-48e8-a00e-ccec8c661a75)
*Account-wise transaction history and running balance*

### 💰 Cash Flow Statement
![Cash Flow](https://github.com/user-attachments/assets/99fb6d32-6b7f-4dd7-9a8d-a70d1b3cff08)
*Cash flow analysis by operating, investing, and financing activities*

### 📱 Mobile Responsive
![Mobile View](https://github.com/user-attachments/assets/71b0d239-fe17-4251-bd19-dda0e1ad0676)
*Fully responsive design*

## 📁 Project Structure

```
Web-Based-Accounting-System/
│
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── README.md             # Project documentation
├── LICENSE               # MIT License
│
├── static/               # Static files
│   └── styles.css       # Main stylesheet
│
├── templates/            # HTML templates
│   ├── base.html        # Base template
│   ├── auth.html        # Authentication pages
│   ├── dashboard.html   # Dashboard page
│   ├── accounts.html    # Account management
│   ├── transactions.html # Transaction pages
│   ├── balance_sheet.html # Balance sheet report
│   ├── income_statement.html # P&L report
│   ├── cashflow_statement.html # Cash flow report
│   ├── ledger.html      # Account ledger
│   └── profile.html     # User profile
│
└── database.db          # SQLite database (auto-generated)
```

## 🤝 Contributing

We welcome contributions to improve the Web-Based Accounting System! Here's how you can help:

### How to Contribute

1. **Fork the Repository**
   ```bash
   git fork https://github.com/GarvRandhar/Web-Based-Accounting-System.git
   ```

2. **Create a Feature Branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

3. **Make Your Changes**
   - Follow the existing code style
   - Add comments for complex logic
   - Test your changes thoroughly

4. **Commit Your Changes**
   ```bash
   git commit -m "Add: Your descriptive commit message"
   ```

5. **Push to Your Fork**
   ```bash
   git push origin feature/your-feature-name
   ```

6. **Create a Pull Request**
   - Provide a clear description of your changes
   - Include screenshots if UI changes are made
   - Reference any related issues

### Development Guidelines

- **Code Style**: Follow PEP 8 for Python code
- **Testing**: Test all new features before submitting
- **Documentation**: Update README if adding new features
- **Responsive Design**: Ensure mobile compatibility

### Areas for Contribution

- 🐛 Bug fixes and improvements
- ✨ New features and enhancements
- 📚 Documentation improvements
- 🎨 UI/UX enhancements
- 🔧 Performance optimizations
- 🌐 Internationalization support

## 📝 License

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details.

```
MIT License

Copyright (c) 2025 Garv Randhar

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
```

## 👨‍💻 Developer

**Garv Randhar**
- GitHub: [@GarvRandhar](https://github.com/GarvRandhar)
- Project Link: [Web-Based Accounting System](https://github.com/GarvRandhar/Web-Based-Accounting-System)

## 🌟 Support

If you find this project helpful, please consider:
- ⭐ **Starring** the repository
- 🐛 **Reporting bugs** via issues
- 💡 **Suggesting features** for future development
- 🤝 **Contributing** to the codebase

## 📊 Project Status

- ✅ **Core Features**: Complete
- ✅ **User Authentication**: Implemented
- ✅ **Financial Reports**: Available
- ✅ **Responsive Design**: Fully responsive
- 🔄 **Ongoing**: Performance optimizations and feature enhancements

---

<div align="center">

**Made with ❤️ for the open source community**

*If you have any questions or suggestions, feel free to open an issue or contact the developer.*

</div>
