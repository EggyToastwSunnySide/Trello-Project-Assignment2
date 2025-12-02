import os
from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlalchemy
from sqlalchemy import text
from collections import defaultdict

app = Flask(__name__)
app.secret_key = 'super_secret_key_trello_app'

# --- KẾT NỐI DB ---
def connect_unix_socket():
    db_user = os.environ["DB_USER"]
    db_pass = os.environ["DB_PASS"]
    db_name = os.environ["DB_NAME"]
    instance_connection_name = os.environ["INSTANCE_CONNECTION_NAME"]
    pool = sqlalchemy.create_engine(
        sqlalchemy.engine.url.URL.create(
            drivername="mysql+pymysql",
            username=db_user,
            password=db_pass,
            database=db_name,
            query={"unix_socket": f"/cloudsql/{instance_connection_name}"},
        )
    )
    return pool

db = connect_unix_socket()

# --- LOGIN & LOGOUT ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user_id = request.form['user_id']
        session['user_id'] = user_id
        try:
            with db.connect() as conn:
                res = conn.execute(text("SELECT FirstName FROM Users WHERE UserID = :uid"), {"uid": user_id})
                user = res.fetchone()
                if user: session['user_name'] = user[0]
        except: pass
        return redirect(url_for('trello_board'))

    try:
        with db.connect() as conn:
            users = conn.execute(text("SELECT UserID, FirstName, LastName, Email FROM Users")).fetchall()
        return render_template('login.html', users=users)
    except Exception as e:
        return f"DB Error: {e}"

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- TRANG CHỦ (BOARD VIEW) ---
@app.route('/')
def trello_board():
    if 'user_id' not in session: return redirect(url_for('login'))
    
    board_id = request.args.get('board_id', default=3, type=int)
    lists_data = defaultdict(list)
    all_boards = []
    current_board_name = "Unknown"
    
    # Biến tính toán tiến độ toàn bảng
    total_cards = 0
    completed_cards = 0
    board_progress = 0
    
    try:
        with db.connect() as conn:
            all_boards = conn.execute(text("SELECT BoardID, Name FROM Board")).fetchall()
            name_res = conn.execute(text("SELECT Name FROM Board WHERE BoardID = :bid"), {"bid": board_id}).fetchone()
            if name_res: current_board_name = name_res[0]

            # completed=None để lấy tất cả
            query = text("CALL SP_Report_BoardDetails(:bid, :completed)")
            result = conn.execute(query, {"bid": board_id, "completed": None})
            rows = result.fetchall()

            for row in rows:
                list_name = row[0]
                is_done = row[7] if len(row) > 7 else 0
                
                total_cards += 1
                if is_done: completed_cards += 1
                
                card_data = {
                    "id": row[1], "title": row[2], "priority": row[3],
                    "due_date": row[4], "assignees": row[5],
                    "progress": row[6] if len(row) > 6 else 0,
                    "is_completed": is_done
                }
                lists_data[list_name].append(card_data)
            
            if total_cards > 0:
                board_progress = int((completed_cards / total_cards) * 100)

    except Exception as e:
        flash(f"Lỗi kết nối: {str(e)}", "error")

    return render_template('board.html', 
                           lists=lists_data, all_boards=all_boards, 
                           current_board_id=board_id, current_board_name=current_board_name,
                           user_name=session.get('user_name'),
                           board_progress=board_progress)

# --- THÊM THẺ (MULTI-ASSIGN) ---
@app.route('/add', methods=['GET', 'POST'])
def add_card():
    if 'user_id' not in session: return redirect(url_for('login'))
    board_id = request.args.get('board_id', default=3, type=int)
    
    if request.method == 'GET':
        with db.connect() as conn:
            lists = conn.execute(text("SELECT ListID, Title FROM Lists WHERE BoardID = :bid ORDER BY Position"), {"bid": board_id}).fetchall()
            users = conn.execute(text("SELECT UserID, FirstName, LastName FROM Users")).fetchall()
        return render_template('add_card.html', lists=lists, users=users, board_id=board_id)
    
    elif request.method == 'POST':
        try:
            # Lấy danh sách ID người được giao (List)
            assignee_ids = request.form.getlist('assignee_ids')
            
            with db.connect() as conn:
                res = conn.execute(text("CALL SP_Card_Insert(:lid, :uid, :title, :desc, :prio, :start, :due)"), {
                    "lid": request.form['list_id'], "uid": session['user_id'],
                    "title": request.form['title'], "desc": request.form['description'], 
                    "prio": request.form['priority'],
                    "start": request.form['start_date'] or None, "due": request.form['due_date'] or None
                })
                new_cid = res.fetchone()[1]
                
                # Vòng lặp insert nhiều người
                for uid in assignee_ids:
                    conn.execute(text("INSERT INTO Card_Member (CardID, UserID, Role) VALUES (:cid, :uid, 'Assignee')"), 
                                 {"cid": new_cid, "uid": uid})
                conn.commit()
            flash("Thêm thẻ thành công!", "success")
            return redirect(url_for('trello_board', board_id=board_id))
        except Exception as e:
            msg = str(e)
            if "reached its CardLimit" in msg: flash("⛔ LỖI: Cột này đã đầy!", "error")
            else: flash(f"Lỗi: {msg}", "error")
            return redirect(url_for('trello_board', board_id=board_id))

# --- SỬA THẺ (MULTI-ASSIGN) ---
@app.route('/edit_card/<int:card_id>', methods=['GET', 'POST'])
def edit_card(card_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    
    if request.method == 'GET':
        try:
            with db.connect() as conn:
                # 1. Thông tin thẻ
                card = conn.execute(text("SELECT * FROM Card WHERE CardID = :cid"), {"cid": card_id}).fetchone()
                
                # 2. Board ID
                list_info = conn.execute(text("SELECT BoardID FROM Lists WHERE ListID = :lid"), {"lid": card.ListID}).fetchone()
                board_id = list_info[0] if list_info else 3

                # 3. Lists & Users
                users = conn.execute(text("SELECT UserID, FirstName, LastName FROM Users")).fetchall()
                lists = conn.execute(text("SELECT ListID, Title FROM Lists WHERE BoardID = :bid ORDER BY Position"), {"bid": board_id}).fetchall()
                
                # 4. Lấy danh sách ID người đang được gán (để highlight)
                assignees_res = conn.execute(text("SELECT UserID FROM Card_Member WHERE CardID = :cid"), {"cid": card_id}).fetchall()
                current_assignee_ids = [row[0] for row in assignees_res]

                card_dict = {
                    "CardID": card.CardID, "Title": card.Title, "Description": card.Description,
                    "Priority": card.Priority, "IsCompleted": card.IsCompleted, 
                    "ListID": card.ListID, "DueDate": card.DueDate,
                    "AssigneeIDs": current_assignee_ids, # List ID [1, 2]
                    "BoardID": board_id
                }
                return render_template('edit_card.html', card=card_dict, users=users, lists=lists)
        except Exception as e:
            flash(f"Lỗi tải thẻ: {e}", "error")
            return redirect(url_for('trello_board'))

    elif request.method == 'POST':
        try:
            redirect_board_id = request.form.get('board_id', 3)
            is_completed = True if request.form.get('is_completed') else False
            assignee_ids = request.form.getlist('assignee_ids') # Lấy danh sách mới

            with db.connect() as conn:
                # 1. Update qua SP
                conn.execute(text("CALL SP_Card_Update(:cid, :title, :prio, :done)"), {
                    "cid": card_id, "title": request.form['title'],
                    "prio": request.form['priority'], "done": is_completed
                })
                # 2. Update thủ công các trường khác
                conn.execute(text("UPDATE Card SET Description = :desc, ListID = :lid, DueDate = :due WHERE CardID = :cid"), {
                    "desc": request.form['description'], "lid": request.form['list_id'],
                    "due": request.form['due_date'] or None, "cid": card_id
                })

                # 3. Cập nhật người làm (Xóa hết cũ -> Thêm mới)
                conn.execute(text("DELETE FROM Card_Member WHERE CardID = :cid"), {"cid": card_id})
                for uid in assignee_ids:
                    conn.execute(text("INSERT INTO Card_Member (CardID, UserID, Role) VALUES (:cid, :uid, 'Assignee')"), 
                                 {"cid": card_id, "uid": uid})
                
                conn.commit()
            flash("Cập nhật thẻ thành công!", "success")
            return redirect(url_for('trello_board', board_id=redirect_board_id))
        except Exception as e:
            msg = str(e)
            if "reached its CardLimit" in msg: flash("⛔ LỖI: Cột đích đã đầy!", "error")
            else: flash(f"Lỗi: {msg}", "error")
            return redirect(url_for('trello_board'))

# --- DELETE & CREATE BOARD (GIỮ NGUYÊN) ---
@app.route('/delete_card/<int:card_id>', methods=['POST'])
def delete_card(card_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    board_id = request.args.get('board_id', 3)
    try:
        with db.connect() as conn:
            conn.execute(text("CALL SP_Card_Delete(:cid)"), {"cid": card_id})
            conn.commit()
        flash("Đã xóa thẻ.", "success")
    except Exception as e: flash(f"Lỗi: {e}", "error")
    return redirect(url_for('trello_board', board_id=board_id))

@app.route('/create_board', methods=['GET', 'POST'])
def create_board():
    if 'user_id' not in session: return redirect(url_for('login'))
    if request.method == 'GET': return render_template('create_board.html')
    elif request.method == 'POST':
        try:
            with db.connect() as conn:
                conn.execute(text("INSERT INTO Board (WorkspaceID, CreatedByUserID, Name, Visibility) VALUES (1, :uid, :name, :vis)"), 
                             {"uid": session['user_id'], "name": request.form['name'], "vis": request.form['visibility']})
                new_bid = conn.execute(text("SELECT LAST_INSERT_ID()")).fetchone()[0]
                conn.execute(text("INSERT INTO Lists (BoardID, Title, Position, CardLimit) VALUES (:bid, 'To Do', 1, 0), (:bid, 'Doing', 2, 5), (:bid, 'Done', 3, 0)"), {"bid": new_bid})
                conn.commit()
            return redirect(url_for('trello_board', board_id=new_bid))
        except: return redirect(url_for('trello_board'))

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8080, debug=True)