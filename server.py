from flask import Flask, request, jsonify, render_template
import sqlite3
import bcrypt

app = Flask(__name__)
users = {
    "admin": "password123"
}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login.html')
def login_page():
    return render_template('login.html')

@app.route('/register.html')
def register_page():
    return render_template('register.html')

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password') 
    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400    
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("SELECT password FROM users WHERE username = ?", (username,))
    result = cursor.fetchone()
    conn.close()
    if result and bcrypt.checkpw(password.encode('utf-8'), result[0]): 
        return jsonify({"message": "Login successful"}), 200
    else:
        return jsonify({"error": "Invalid credentials"}), 401

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username')
    password = data.get('password') 
    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400    
    password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT username FROM users WHERE username = ?", (username,))    
        result = cursor.fetchone()
        if result:
            return jsonify({"error": "Username already exists"}), 409
        else:
            cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", 
                        (username, password_hash))
            conn.commit()
            conn.close()
            return jsonify({"message": "Login successful"}), 200
    
    except sqlite3.IntegrityError:
        return jsonify({"error": "Username already exists"}), 409


if __name__ == '__main__':
    app.run(debug=True)