from flask import Flask, render_template, request, redirect, session, jsonify, url_for
from datetime import datetime, timedelta
import sqlite3
import random
import os

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Configurações de Gamificação
LEVEL_THRESHOLDS = [
    0, 100, 300, 600, 1000, 1500, 2100, 2800, 3600, 4500
]

ACHIEVEMENTS = {
    'first_task': {
        'name': 'Primeiro Passo',
        'desc': 'Complete sua primeira tarefa',
        'icon': '🎯',
        'points': 50
    },
    'streak_3': {
        'name': 'Consistente',
        'desc': 'Mantenha uma sequência de 3 dias',
        'icon': '🔥',
        'points': 100
    },
    'streak_7': {
        'name': 'Dedicado',
        'desc': 'Mantenha uma sequência de 7 dias',
        'icon': '⭐',
        'points': 200
    },
    'all_tasks': {
        'name': 'Super Produtivo',
        'desc': 'Complete todas as tarefas em um dia',
        'icon': '🏆',
        'points': 150
    },
    'level_5': {
        'name': 'Evoluindo',
        'desc': 'Alcance o nível 5',
        'icon': '📈',
        'points': 300
    },
    'happy_pet': {
        'name': 'Melhor Amigo',
        'desc': 'Mantenha seu pet 100% feliz',
        'icon': '❤️',
        'points': 100
    }
}

DAILY_TASKS = [
    {"name": "Beber água 💧", "points": 10, "category": "saúde"},
    {"name": "Exercício leve 🏃", "points": 20, "category": "saúde"},
    {"name": "Meditar 🧘", "points": 15, "category": "bem-estar"},
    {"name": "Tomar banho 🚿", "points": 10, "category": "higiene"},
    {"name": "Escovar os dentes 🦷", "points": 10, "category": "higiene"},
    {"name": "Arrumar a cama 🛏️", "points": 10, "category": "casa"},
    {"name": "Tomar sol ☀️", "points": 15, "category": "saúde"},
    {"name": "Ouvir música 🎵", "points": 10, "category": "bem-estar"},
    {"name": "Organizar espaço 🧹", "points": 15, "category": "casa"},
    {"name": "Ler algo 📚", "points": 20, "category": "desenvolvimento"}
]

def get_db():
    conn = sqlite3.connect('companion.db')
    conn.row_factory = sqlite3.Row
    return conn

def calculate_level_progress(points):
    level = 1
    for i, threshold in enumerate(LEVEL_THRESHOLDS):
        if points >= threshold:
            level = i + 1
        else:
            break
    
    current_threshold = LEVEL_THRESHOLDS[level-1] if level > 0 else 0
    next_threshold = LEVEL_THRESHOLDS[level] if level < len(LEVEL_THRESHOLDS) else LEVEL_THRESHOLDS[-1]
    
    if next_threshold == current_threshold:
        progress = 100
    else:
        progress = ((points - current_threshold) / (next_threshold - current_threshold)) * 100
    
    return {
        'level': level,
        'progress': min(progress, 100),
        'next_level': min(level + 1, len(LEVEL_THRESHOLDS)),
        'points_needed': max(0, next_threshold - points)
    }

def init_db():
    if os.path.exists('companion.db'):
        os.remove('companion.db')
    
    conn = get_db()
    c = conn.cursor()
    
    c.executescript('''
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            points INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1,
            exp INTEGER DEFAULT 0,
            streak INTEGER DEFAULT 0,
            last_login TEXT,
            pet_name TEXT DEFAULT 'Miau',
            pet_happiness INTEGER DEFAULT 100
        );

        CREATE TABLE achievements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            achievement_type TEXT,
            date_earned TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE daily_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            task_name TEXT,
            completed INTEGER DEFAULT 0,
            date TEXT,
            points INTEGER,
            category TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE daily_rewards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            day INTEGER,
            claimed INTEGER DEFAULT 0,
            date TEXT,
            points INTEGER,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    ''')
    
    conn.commit()
    conn.close()

def check_achievements(user_id):
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    today = datetime.now().strftime('%Y-%m-%d')
    
    achieved = conn.execute('SELECT achievement_type FROM achievements WHERE user_id = ?',
                          (user_id,)).fetchall()
    achieved = [a['achievement_type'] for a in achieved]
    
    new_achievements = []
    
    # Verificar cada conquista
    if 'first_task' not in achieved:
        tasks_completed = conn.execute('SELECT COUNT(*) as count FROM daily_tasks WHERE user_id = ? AND completed = 1',
                                     (user_id,)).fetchone()['count']
        if tasks_completed > 0:
            new_achievements.append('first_task')
    
    if 'streak_3' not in achieved and user['streak'] >= 3:
        new_achievements.append('streak_3')
    
    if 'streak_7' not in achieved and user['streak'] >= 7:
        new_achievements.append('streak_7')
    
    if 'all_tasks' not in achieved:
        today_tasks = conn.execute('''SELECT COUNT(*) as count FROM daily_tasks 
                                    WHERE user_id = ? AND date = ? AND completed = 1''',
                                 (user_id, today)).fetchone()['count']
        if today_tasks == len(DAILY_TASKS):
            new_achievements.append('all_tasks')
    
    if 'level_5' not in achieved and user['level'] >= 5:
        new_achievements.append('level_5')
    
    if 'happy_pet' not in achieved and user['pet_happiness'] == 100:
        new_achievements.append('happy_pet')
    
    # Registrar novas conquistas
    for achievement in new_achievements:
        conn.execute('INSERT INTO achievements (user_id, achievement_type, date_earned) VALUES (?, ?, ?)',
                    (user_id, achievement, today))
        points = ACHIEVEMENTS[achievement]['points']
        conn.execute('UPDATE users SET points = points + ? WHERE id = ?',
                    (points, user_id))
    
    conn.commit()
    conn.close()
    return new_achievements

@app.route('/')
def home():
    if 'user_id' not in session:
        return redirect('/login')
    
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE id = ?', 
                       (session['user_id'],)).fetchone()
    
    if not user:
        session.clear()
        return redirect('/login')
    
    today = datetime.now().date()
    last_login = datetime.strptime(user['last_login'], '%Y-%m-%d').date() if user['last_login'] else None
    
    if last_login != today:
        if last_login and (today - last_login).days == 1:
            conn.execute('UPDATE users SET streak = streak + 1 WHERE id = ?', 
                        (session['user_id'],))
        elif last_login and (today - last_login).days > 1:
            conn.execute('UPDATE users SET streak = 0 WHERE id = ?', 
                        (session['user_id'],))
        
        conn.execute('UPDATE users SET last_login = ? WHERE id = ?',
                    (today.strftime('%Y-%m-%d'), session['user_id']))
        conn.commit()
    
    tasks = conn.execute('''SELECT * FROM daily_tasks 
                           WHERE user_id = ? AND date = ?''',
                        (session['user_id'], today.strftime('%Y-%m-%d'))).fetchall()
    
    if not tasks:
        for task in DAILY_TASKS:
            conn.execute('''INSERT INTO daily_tasks 
                          (user_id, task_name, date, points, category)
                          VALUES (?, ?, ?, ?, ?)''',
                       (session['user_id'], task['name'], 
                        today.strftime('%Y-%m-%d'),
                        task['points'], task['category']))
        conn.commit()
        tasks = conn.execute('''SELECT * FROM daily_tasks 
                              WHERE user_id = ? AND date = ?''',
                           (session['user_id'], today.strftime('%Y-%m-%d'))).fetchall()
    
    achievements = conn.execute('SELECT achievement_type FROM achievements WHERE user_id = ?',
                              (session['user_id'],)).fetchall()
    achieved = [a['achievement_type'] for a in achievements]
    
    daily_reward = conn.execute('''SELECT * FROM daily_rewards 
                                  WHERE user_id = ? AND date = ?''',
                               (session['user_id'], today.strftime('%Y-%m-%d'))).fetchone()
    
    conn.close()
    
    level_progress = calculate_level_progress(user['points'])
    
    return render_template('home.html',
                         user=user,
                         tasks=tasks,
                         achievements=ACHIEVEMENTS,
                         achieved=achieved,
                         daily_reward=daily_reward,
                         level_progress=level_progress)

@app.route('/complete_task', methods=['POST'])
def complete_task():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Não autenticado'})
    
    task_id = request.form.get('task_id')
    conn = get_db()
    
    task = conn.execute('SELECT points FROM daily_tasks WHERE id = ?', (task_id,)).fetchone()
    if task:
        conn.execute('UPDATE daily_tasks SET completed = 1 WHERE id = ? AND user_id = ?',
                    (task_id, session['user_id']))
        conn.execute('UPDATE users SET points = points + ? WHERE id = ?',
                    (task['points'], session['user_id']))
        conn.commit()
        
        new_achievements = check_achievements(session['user_id'])
        conn.close()
        
        return jsonify({
            'success': True,
            'points': task['points'],
            'new_achievements': new_achievements
        })
    
    conn.close()
    return jsonify({'success': False, 'message': 'Tarefa não encontrada'})

@app.route('/claim_daily_reward', methods=['POST'])
def claim_daily_reward():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Não autenticado'})
    
    conn = get_db()
    today = datetime.now().date()
    
    reward = conn.execute('''SELECT * FROM daily_rewards 
                            WHERE user_id = ? AND date = ?''',
                         (session['user_id'], today.strftime('%Y-%m-%d'))).fetchone()
    
    if reward and reward['claimed']:
        conn.close()
        return jsonify({'success': False, 'message': 'Recompensa já recebida hoje'})
    
    user = conn.execute('SELECT streak FROM users WHERE id = ?',
                       (session['user_id'],)).fetchone()
    streak = user['streak']
    
    base_points = 50
    streak_bonus = min(streak * 5, 50)
    total_points = base_points + streak_bonus
    
    if not reward:
        conn.execute('''INSERT INTO daily_rewards 
                       (user_id, day, claimed, date, points)
                       VALUES (?, ?, 1, ?, ?)''',
                    (session['user_id'], streak + 1,
                     today.strftime('%Y-%m-%d'), total_points))
    else:
        conn.execute('UPDATE daily_rewards SET claimed = 1 WHERE id = ?',
                    (reward['id'],))
    
    conn.execute('UPDATE users SET points = points + ? WHERE id = ?',
                (total_points, session['user_id']))
    
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True,
        'points': total_points,
        'message': f'Recebeu {total_points} pontos! (Bônus de streak: +{streak_bonus})'
    })

@app.route('/pet_interaction', methods=['POST'])
def pet_interaction():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Não autenticado'})
    
    conn = get_db()
    happiness_increase = random.randint(5, 15)
    
    conn.execute('''UPDATE users 
                    SET pet_happiness = MIN(pet_happiness + ?, 100)
                    WHERE id = ?''',
                (happiness_increase, session['user_id']))
    conn.commit()
    
    happiness = conn.execute('SELECT pet_happiness FROM users WHERE id = ?',
                           (session['user_id'],)).fetchone()['pet_happiness']
    
    if happiness == 100:
        check_achievements(session['user_id'])
    
    conn.close()
    
    return jsonify({
        'success': True,
        'happiness': happiness,
        'message': random.choice([
            "Miau! 😺",
            "Purrrr... 😸",
            "Ronron... 😽",
            "*lambida carinhosa* 😺",
            "Miau miau! 🐱"
        ])
    })

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE username = ? AND password = ?',
                          (username, password)).fetchone()
        conn.close()
        
        if user:
            session['user_id'] = user['id']
            return redirect('/')
        return render_template('login.html', error='Usuário ou senha inválidos')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db()
        try:
            conn.execute('''INSERT INTO users 
                          (username, password, last_login)
                          VALUES (?, ?, ?)''',
                       (username, password, datetime.now().strftime('%Y-%m-%d')))
            conn.commit()
            conn.close()
            return redirect('/login')
        except sqlite3.IntegrityError:
            conn.close()
            return render_template('register.html', error='Nome de usuário já existe')
        
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

if __name__ == '__main__':
    init_db()
    app.run(debug=True)