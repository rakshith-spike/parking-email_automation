 🚗 Parking Email Automation System

A full-stack web application that automates parking management and sends email notifications for vehicle entry, exit, and daily summaries.

---

📌 Features

* 🚘 Vehicle Entry & Exit Tracking
* 📧 Automated Email Notifications
* 🕒 Daily Summary Reports
* 🔍 Search & View Parking Records
* 🌐 Deployed using AWS (S3 + EC2)
* ⚡ FastAPI backend for high performance

---

🏗️ Tech Stack

Frontend

* HTML
* CSS
* JavaScript
* Hosted on AWS S3

Backend

* Python
* FastAPI
* Uvicorn

 Cloud & Deployment

* AWS EC2 (Backend Hosting)
* AWS S3 (Frontend Hosting)
* Elastic IP (Static Backend URL)
* PM2 (Process Manager for automation)

---

⚙️ Project Structure

parking-email-automation/
│
├── frontend/
│   ├── index.html
│   ├── style.css
│   ├── script.js
│
├── backend/
│   ├── main.py
│   ├── requirements.txt
│
└── README.md


---

 🚀 Setup Instructions

 1️⃣ Clone the Repository


git clone https://github.com/rakshith-spike/parking-email-automation.git
cd parking-email-automation


---

 2️⃣ Backend Setup (FastAPI)


cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt


---

3️⃣ Run Backend Locally


uvicorn main:app --reload


---

 4️⃣ Frontend Setup

* Open index.html in browser
  OR
* Deploy using AWS S3

---

🌐 Deployment (AWS)

Backend (EC2)

* Launch EC2 instance (Ubuntu)
* Install Python & dependencies
* Run FastAPI using:


uvicorn main:app --host 0.0.0.0 --port 8000


---

 Automation (PM2)


pm2 start "venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000" --name backend
pm2 save
pm2 startup


---

Frontend (S3)

* Upload index.html to S3 bucket
* Enable static website hosting
* Update backend URL in frontend

---

🔗 API Example


GET /data
POST /park
POST /exit


---

 🧠 How It Works

1. User enters vehicle details in frontend
2. Data is sent to FastAPI backend
3. Backend processes and stores data
4. Email is triggered automatically
5. Daily summaries are generated

---



 🔒 Future Improvements

* Add authentication (Login/Signup)
* Use database (MongoDB / PostgreSQL)
* Add payment integration
* Deploy with custom domain + HTTPS

---

👨‍💻 Author

Rakshith K R 

---

⭐ Acknowledgements

* FastAPI Documentation
* AWS Cloud Services
* OpenAI & developer tools

---

## 📬 Contact

For queries or collaboration, feel free to reach out.

---

⭐ If you like this project, don’t forget to star the repository!
