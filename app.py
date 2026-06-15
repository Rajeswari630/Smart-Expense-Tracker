from flask import Flask, render_template, request, redirect, session
import mysql.connector
import pandas as  pd
from werkzeug.security import generate_password_hash, check_password_hash
import config
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from datetime import date
from flask import send_file
import os
app = Flask(__name__)
app.secret_key = "expense_tracker_secret_key"

# Database Connection
db = mysql.connector.connect(
    host=config.DB_HOST,
    user=config.DB_USER,
    password=config.DB_PASSWORD,
    database=config.DB_NAME
)

cursor = db.cursor()
@app.route('/download_pdf')
def download_pdf():
    user_id = session['user_id']

    # Get expenses
    cursor.execute("""
        SELECT category, SUM(amount)
        FROM expenses
        WHERE user_id=%s
        GROUP BY category
    """, (user_id,))
    data = cursor.fetchall()

    total_expense = 0
    for row in data:
        total_expense += float(row[1])

    income = 50000  # you can change or take from DB later
    savings = income - total_expense

    file_name = "expense_report.pdf"
    c = canvas.Canvas(file_name, pagesize=letter)

    c.setFont("Helvetica-Bold", 16)
    c.drawString(200, 750, "Expense Tracker Report")

    c.setFont("Helvetica", 12)
    c.drawString(50, 700, f"Date: {date.today()}")

    c.drawString(50, 670, f"Total Income: {income}")
    c.drawString(50, 650, f"Total Expenses: {total_expense}")
    c.drawString(50, 630, f"Savings: {savings}")

    y = 580
    c.drawString(50, y, "Category Wise Expenses:")

    for row in data:
        y -= 20
        c.drawString(70, y, f"{row[0]} : {row[1]}")

    c.save()

    return send_file(file_name, as_attachment=True)
@app.route('/download_excel')
def download_excel():
    cursor = db.cursor()
    cursor.execute(
        "SELECT title, category, amount, date FROM expenses WHERE user_id=%s",
        (session['user_id'],)
    )
    data = cursor.fetchall()

    df = pd.DataFrame(data, columns=['Title','Category','Amount','Date'])
    df.to_excel("expenses.xlsx", index=False)

    return send_file("expenses.xlsx", as_attachment=True)


# ---------------- HOME ----------------
@app.route('/')
def home():
    return redirect('/login')


# ---------------- REGISTER ----------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])

        cursor.execute(
            "INSERT INTO users (name, email, password) VALUES (%s, %s, %s)",
            (name, email, password)
        )
        db.commit()

        return redirect('/login')

    return render_template('register.html')


# ---------------- LOGIN ----------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
        user = cursor.fetchone()

        if user and check_password_hash(user[3], password):
            session['user_id'] = user[0]
            return redirect('/dashboard')

        return "Invalid login credentials"

    return render_template('login.html')


# ---------------- DASHBOARD ----------------
@app.route('/dashboard')
def dashboard():

    if 'user_id' not in session:
        return redirect('/login')

    cursor = db.cursor()

    # ---------------- FILTER ----------------
    filter_type = request.args.get('filter')

    query = "SELECT * FROM expenses WHERE user_id=%s"
    values = [session['user_id']]

    if filter_type == "today":
        query += " AND DATE(date)=CURDATE()"

    elif filter_type == "yesterday":
        query += " AND DATE(date)=CURDATE() - INTERVAL 1 DAY"

    elif filter_type == "week":
        query += " AND date >= CURDATE() - INTERVAL 7 DAY"

    cursor.execute(query, tuple(values))
    expenses = cursor.fetchall()

    # ---------------- TOTAL ----------------
    cursor.execute(
        "SELECT SUM(amount) FROM expenses WHERE user_id=%s",
        (session['user_id'],)
    )
    total = cursor.fetchone()[0] or 0

    # ---------------- MONTHLY ----------------
    cursor.execute("""
        SELECT SUM(amount) FROM expenses
        WHERE user_id=%s
        AND MONTH(date)=MONTH(CURDATE())
        AND YEAR(date)=YEAR(CURDATE())
    """, (session['user_id'],))
    monthly = cursor.fetchone()[0] or 0

    # ---------------- YEARLY ----------------
    cursor.execute("""
        SELECT SUM(amount) FROM expenses
        WHERE user_id=%s
        AND YEAR(date)=YEAR(CURDATE())
    """, (session['user_id'],))
    yearly = cursor.fetchone()[0] or 0

    # ---------------- INCOME ----------------
    cursor.execute(
        "SELECT SUM(amount) FROM income WHERE user_id=%s",
        (session['user_id'],)
    )
    income = cursor.fetchone()[0] or 0

    # ---------------- SAVINGS ----------------
    savings = income - total

    # ---------------- NOTIFICATIONS ----------------
    notifications = []
    budget = 5000

    if total > budget:
        notifications.append("🚨 Budget Exceeded!")
    elif total >= 0.8 * budget:
        notifications.append("⚠️ Budget 80% completed")
    elif total > 2000:
        notifications.append("⚠️ You spent more than 2000")

    if savings < 1000:
        notifications.append("❗ Low savings")

    # ---------------- RETURN ----------------
    return render_template(
        'dashboard.html',
        expenses=expenses,
        total=total,
        monthly=monthly,
        yearly=yearly,
        income=income,
        savings=savings,
        notifications=notifications
    )
@app.route('/piechart')
def piechart():
    user_id = session['user_id']

    cursor.execute("""
        SELECT category, SUM(amount)
        FROM expenses
        WHERE user_id=%s
        GROUP BY category
    """, (user_id,))

    data = cursor.fetchall()

    categories = []
    values = []

    for row in data:
        categories.append(row[0])
        values.append(float(row[1]))

    return render_template("piechart.html", categories=categories,values=values)


# ---------------- ADD EXPENSE ----------------
@app.route('/add_expense', methods=['GET', 'POST'])
def add_expense():
    if 'user_id' not in session:
        return redirect('/login')

    if request.method == 'POST':
        title = request.form['title']
        category = request.form['category']
        amount = request.form['amount']
        date = request.form['date']

        cursor.execute("""
            INSERT INTO expenses (user_id, title, category, amount, date)
            VALUES (%s, %s, %s, %s, %s)
        """, (session['user_id'], title, category, amount, date))

        db.commit()
        return redirect('/dashboard')

    return render_template('add_expense.html')


# ---------------- DELETE EXPENSE ----------------
@app.route('/delete/<int:id>')
def delete(id):
    cursor.execute(
        "DELETE FROM expenses WHERE id=%s AND user_id=%s",
        (id, session['user_id'])
    )
    db.commit()
    return redirect('/dashboard')


# ---------------- EDIT EXPENSE ----------------
@app.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit(id):
    if request.method == 'POST':
        title = request.form['title']
        category = request.form['category']
        amount = request.form['amount']
        date = request.form['date']

        cursor.execute("""
            UPDATE expenses
            SET title=%s, category=%s, amount=%s, date=%s
            WHERE id=%s AND user_id=%s
        """, (title, category, amount, date, id, session['user_id']))

        db.commit()
        return redirect('/dashboard')

    cursor.execute(
        "SELECT * FROM expenses WHERE id=%s AND user_id=%s",
        (id, session['user_id'])
    )
    expense = cursor.fetchone()

    return render_template('edit_expense.html', expense=expense)


# ---------------- LOGOUT ----------------
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')


# ---------------- RUN APP ----------------
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)