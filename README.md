# Accounting Pro

[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-live-success.svg)](https://web-based-accounting-system.onrender.com)
[![Live Demo](https://img.shields.io/badge/demo-online-brightgreen)](https://web-based-accounting-system.onrender.com)

## Enterprise-Grade Web Accounting for Modern Operations
Accounting Pro is a highly robust, production-ready accounting engine built to mirror high-end ERP capabilities within a streamlined, dark-themed interface. Underneath the hood, it rigidly enforces GAAP / IFRS accounting standards, ensuring that data hygiene is mathematically pure right down to individual ledger postings.

The system natively manages the full lifecycle of financial operations: complete Chart of Accounts configurations, Accounts Payable/Receivable, Tax mapping, dynamically evaluated FIFO Inventory stock layers, Payroll, Fixed Asset Depreciation, and native Multi-Currency translations automatically bridging foreign transactions into your structural Base Currency.

## Live Demo
Experience the deployed application here:
**[https://web-based-accounting-system.onrender.com](https://web-based-accounting-system.onrender.com)**

---

## 🌟 Key Features & Compliance
- **Mathematically Pure Double-Entry**: Native enforcement prevents any journal entry from saving unless debits and credits perfectly intersect within a strict 0.01 tolerance bound.
- **Dynamic FIFO & Moving Average**: The physical inventory tracker supports true GAAP-compliant FIFO valuation arrays, dynamically routing withdrawal algorithms to isolate chronological cost layers sequentially. 
- **Base Currency FX Mapping**: Invoices and Bills authored in EUR or GBP are internally mapped against real-time Exchange Rates so that their structural Journal Entries flow purely into your Base Currency (e.g., USD), rendering a perfect Trial Balance. 
- **Idempotent Year-End Closures**: Mechanically hardened protection preventing duplicate retained-earnings injections during repetitive FY closures or workflow resets.
- **Robust Role-Based Access Control (RBAC)**: Securely bifurcates execution states between `Admin`, `Accountant`, and `Viewer`.

---

## 📸 Core Dashboards

### Dashboard
<p align="center">
  <img src="https://github.com/user-attachments/assets/a20b970f-63d2-4896-a387-b958f9403116" alt="Dashboard" width="100%">
</p>

### Journal Entries
<p align="center">
  <img src="https://github.com/user-attachments/assets/c0372faa-62c1-47e9-9274-761a3d46ea73" alt="Journal Entries" width="100%">
</p>

### Chart of Accounts
<p align="center">
  <img src="https://github.com/user-attachments/assets/13cab52a-3eef-4b9a-be8f-88a268a6801a" alt="Chart of Accounts" width="100%">
</p>

### Currencies and Exchange Rates
<p align="center">
  <img src="https://github.com/user-attachments/assets/ab07dd17-3ad3-4633-a4d0-b88bfa2420a7" alt="Currencies and Exchange Rates" width="100%">
</p>

### Settings
<p align="center">
  <img src="https://github.com/user-attachments/assets/e4297876-9b90-4b81-97e2-cd72bdb9042d" alt="Settings" width="100%">
</p>

---

## 🛠 Tech Stack & Architecture
- **Backend**: Python 3, Flask, SQLAlchemy ORM (SQLite / PostgreSQL Support).
- **Frontend**: Vanilla Javascript, CSS3 (Native CSS Variables for responsive Dark Modes), HTML5.
- **Security**: Flask-Login, Flask-Limiter (Brute-Force DDoSing protection natively active on Authentication APIs), and PyJWT (Tokenized Email generation hooks).
- **Auditing**: Dedicated `AuditService` pipeline recursively logging state mutations across object deletions, creations, and transactional rollbacks.

## 🚀 Getting Started
1. Clone the repository:
   ```bash
   git clone https://github.com/GarvRandhar/Web-Based-Accounting-System.git
   ```
2. Navigate to the project directory:
   ```bash
   cd Web-Based-Accounting-System
   ```
3. Set your internal dependencies:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
4. Initialzie the database architecture:
   ```bash
   python init_db.py
   ```
5. Run the web server:
   ```bash
   python run.py
   ```

---

## 🔐 Security & Access Control

### Role Tiers
- `admin`
  - Total system overrides. Capable of invoking system settings, sending programmatic JWT email invitations, and terminating accounts.
- `accountant`
  - Capable of creating, voiding, or mapping all operational accounting tasks (Bills, Payroll, Journal Entries). Cannot mutate system settings.
- `viewer`
  - Strictly limited to `GET` network operations. Can preview reports and dashboards safely without database mutating execution pathways.

### Invitation-Only Onboarding
- Self-registration is mechanically blocked to prevent internet skimming bots.
- Admins invite users exclusively from **Admin Panel → User Management** (`/admin/users`).
- The backend leverages `smtplib` to dynamically fire a PyJWT encoded secure link to the invited user via email to prompt secure password generation.

### Exposed Internal API Services
- `POST /api/admin/invite`
- `GET /api/admin/users`
- `DELETE /api/admin/users/<id>` (Tied entirely into `AuditService` monitoring)
- `POST /api/admin/resend-invite/<id>`
- `POST /api/auth/change-password`

---

## ⚙️ Environment Variables

Configure these `.env` variables before triggering production deployment wrappers (e.g. Docker, Gunicorn):

# Core Application Base
- `SECRET_KEY` (MUST be altered in production to seal Flask Client cookies)
- `DATABASE_URL` (Capable of mapping strictly to Postgres schemas internally)
- `SYSTEM_NAME` (e.g., `Globex Corp ERP`)
- `APP_BASE_URL` (e.g., `https://accounting.yourdomain.com`)

# Network Protections
- `JWT_EXP_HOURS` (default: `12`)
- `INVITE_RATE_LIMIT` (default: `5 per minute`)

# Secure SMTP Configurations (For Admin Invites)
- `MAIL_SERVER` (e.g. `smtp.gmail.com`)
- `MAIL_PORT` (default: `587`)
- `MAIL_USE_TLS` (default: `true`)
- `MAIL_USERNAME`
- `MAIL_PASSWORD` (Use specialized App Passwords if leveraging Gmail/SES)
- `MAIL_SENDER` (defaults to `MAIL_USERNAME`)

*(If `MAIL_SERVER` is missing from the environment architecture, the system operates in fallback mode, spitting the generated invitation URLs securely out to the console logs.)*

---

## Contributing
Contributions are welcome. Feel free to fork the repository and open a pull request with targeted architectural enhancements or structural algorithm tweaks.

## License
This project is licensed under the MIT License. See the LICENSE file for details.

## Contact
For system queries or implementation discussions, please reach out to **GarvRandhar**.
