import os
from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlalchemy
from sqlalchemy import text
from collections import OrderedDict

app = Flask(__name__)
# CRITICAL: Secret key needed for session management and flash messages
app.secret_key = 'super_secret_key_trello_app'

# --- DATABASE CONNECTION SETUP ---
def connect_unix_socket():
    """Initializes a connection pool for a Cloud SQL instance of MySQL."""
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

# Initialize the global connection pool
db = connect_unix_socket()

# --- AUTHENTICATION ROUTES ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handles user login."""
    if request.method == 'POST':
        user_id = request.form['user_id']
        session['user_id'] = user_id
        try:
            with db.connect() as conn:
                # Fetch user name for display
                res = conn.execute(text("SELECT FirstName FROM Users WHERE UserID = :uid"), {"uid": request.form['user_id']})
                user = res.fetchone()
                if user: 
                    session['user_name'] = user[0]
        except: 
            pass
        return redirect(url_for('trello_board'))

    # GET request: Show login form with user list
    try:
        with db.connect() as conn:
            users = conn.execute(text("SELECT UserID, FirstName, LastName, Email FROM Users")).fetchall()
        return render_template('login.html', users=users)
    except Exception as e: 
        return f"DB Connection Error: {e}"

@app.route('/logout')
def logout():
    """Clears session and redirects to login."""
    session.clear()
    return redirect(url_for('login'))

# --- MAIN BOARD VIEW ---
@app.route('/')
def trello_board():
    """Displays the main Kanban board."""
    if 'user_id' not in session: return redirect(url_for('login'))
    
    board_id = request.args.get('board_id', default=3, type=int)
    
    # Use OrderedDict to ensure columns appear in correct position order
    lists_data = OrderedDict()
    all_boards = []
    current_board_name = "Unknown"
    user_permission = "View"
    
    # Stats variables
    total_cards = 0; completed_cards = 0; board_progress = 0
    
    try:
        with db.connect() as conn:
            # 1. Get Board List (for navigation menu)
            all_boards = conn.execute(text("SELECT BoardID, Name FROM Board")).fetchall()
            
            # 2. Get Current Board Name
            name_res = conn.execute(text("SELECT Name FROM Board WHERE BoardID = :bid"), {"bid": board_id}).fetchone()
            if name_res: current_board_name = name_res[0]
            
            # 3. Check Permissions
            perm_res = conn.execute(text("SELECT Permission FROM Board_Member WHERE BoardID = :bid AND UserID = :uid"), 
                                    {"bid": board_id, "uid": session['user_id']}).fetchone()
            if perm_res:
                user_permission = perm_res[0]

            # 4. Fetch LIST Structure (to show empty columns)
            lists_res = conn.execute(text("SELECT ListID, Title, CardLimit FROM Lists WHERE BoardID = :bid ORDER BY Position"), {"bid": board_id}).fetchall()
            
            # Initialize dictionary keys
            for lst in lists_res:
                lists_data[(lst.ListID, lst.Title, lst.CardLimit)] = []

            # 5. Fetch CARDS using Stored Procedure
            query = text("CALL SP_Report_BoardDetails(:bid, :completed)")
            result = conn.execute(query, {"bid": board_id, "completed": None}) # None = Get all cards
            rows = result.fetchall()

            for row in rows:
                # Map raw SQL result to dictionary keys
                # row[0] is ListName (Title). We find the matching key in our OrderedDict.
                target_key = None
                for key in lists_data.keys():
                    if key[1] == row[0]: # key[1] is Title
                        target_key = key
                        break
                
                if target_key:
                    is_done = row[7] if len(row) > 7 else 0
                    total_cards += 1
                    if is_done: completed_cards += 1
                    
                    card_data = {
                        "id": row[1], 
                        "title": row[2], 
                        "priority": row[3],
                        "due_date": row[4], 
                        "assignees": row[5],
                        "progress": row[6] if len(row) > 6 else 0, # Percentage from SQL Function
                        "is_completed": is_done,
                        "mod_time": row[8] if len(row) > 8 else "", # Formatted Time
                        "mod_user": row[9] if len(row) > 9 else ""  # Modifier Name
                    }
                    lists_data[target_key].append(card_data)
            
            # Calculate global progress
            if total_cards > 0: 
                board_progress = int((completed_cards / total_cards) * 100)

    except Exception as e:
        flash(f"Error loading board: {str(e)}", "error")

    return render_template('board.html', 
                           lists=lists_data, all_boards=all_boards, 
                           current_board_id=board_id, current_board_name=current_board_name,
                           user_name=session.get('user_name'), board_progress=board_progress,
                           user_permission=user_permission)

# --- LIST MANAGEMENT ---
@app.route('/create_list', methods=['POST'])
def create_list():
    board_id = request.form['board_id']
    title = request.form['title']
    try:
        with db.connect() as conn:
            # Auto-increment Position
            pos_res = conn.execute(text("SELECT MAX(Position) FROM Lists WHERE BoardID = :bid"), {"bid": board_id}).fetchone()
            new_pos = (pos_res[0] or 0) + 1
            
            conn.execute(text("INSERT INTO Lists (BoardID, Title, Position, CardLimit) VALUES (:bid, :title, :pos, 0)"), 
                         {"bid": board_id, "title": title, "pos": new_pos})
            conn.commit()
        flash("List added successfully!", "success")
    except Exception as e: flash(f"Error {e}", "error")
    return redirect(url_for('trello_board', board_id=board_id))

@app.route('/delete_list/<int:list_id>', methods=['POST'])
def delete_list(list_id):
    board_id = request.args.get('board_id')
    try:
        with db.connect() as conn:
            conn.execute(text("DELETE FROM Lists WHERE ListID = :lid"), {"lid": list_id})
            conn.commit()
        flash("List deleted successfully!", "success")
    except Exception as e: flash(f"Error {e}", "error")
    return redirect(url_for('trello_board', board_id=board_id))

@app.route('/edit_list/<int:list_id>', methods=['POST'])
def edit_list(list_id):
    board_id = request.form['board_id']
    new_title = request.form['title']
    try:
        with db.connect() as conn:
            conn.execute(text("UPDATE Lists SET Title = :title WHERE ListID = :lid"), {"title": new_title, "lid": list_id})
            conn.commit()
        flash("List updated successfully!", "success")
    except Exception as e: flash(f"Error {e}", "error")
    return redirect(url_for('trello_board', board_id=board_id))

# --- BOARD MANAGEMENT ---
@app.route('/edit_board/<int:board_id>', methods=['POST'])
def edit_board(board_id):
    new_name = request.form['name']
    try:
        with db.connect() as conn:
            conn.execute(text("UPDATE Board SET Name = :name WHERE BoardID = :bid"), {"name": new_name, "bid": board_id})
            conn.commit()
        flash("Board updated successfully!", "success")
    except Exception as e: flash(f"Error {e}", "error")
    return redirect(url_for('trello_board', board_id=board_id))

@app.route('/delete_board/<int:board_id>', methods=['POST'])
def delete_board(board_id):
    try:
        with db.connect() as conn:
            conn.execute(text("DELETE FROM Board WHERE BoardID = :bid"), {"bid": board_id})
            conn.commit()
        flash("Board deleted successfully!", "success")
        return redirect(url_for('trello_board')) 
    except Exception as e: 
        flash(f"Error {e}", "error")
        return redirect(url_for('trello_board', board_id=board_id))

# --- CARD OPERATIONS ---
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
            assignee_ids = request.form.getlist('assignee_ids')
            with db.connect() as conn:
                # 1. Call SP to Insert Card
                res = conn.execute(text("CALL SP_Card_Insert(:lid, :uid, :title, :desc, :prio, :start, :due)"), {
                    "lid": request.form['list_id'], "uid": session['user_id'],
                    "title": request.form['title'], "desc": request.form['description'], 
                    "prio": request.form['priority'], "start": request.form['start_date'] or None, "due": request.form['due_date'] or None
                })
                new_cid = res.fetchone()[1]
                
                # 2. Insert Multiple Assignees
                for uid in assignee_ids:
                    conn.execute(text("INSERT INTO Card_Member (CardID, UserID, Role) VALUES (:cid, :uid, 'Assignee')"), {"cid": new_cid, "uid": uid})
                conn.commit()
            
            flash("Card added successfully!", "success")
            return redirect(url_for('trello_board', board_id=board_id))
        
        except Exception as e:
            # Error Handling for Triggers/Procedures
            msg = str(e)
            if "reached its CardLimit" in msg: flash("⛔ Error: Card count exceeded in list!", "error")
            elif "ACCESS DENIED" in msg: flash("⛔ Access Denied: You don't have permission to add a card to this list!", "error")
            else: flash(f"Error {msg}", "error")
            return redirect(url_for('trello_board', board_id=board_id))

@app.route('/edit_card/<int:card_id>', methods=['GET', 'POST'])
def edit_card(card_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    
    if request.method == 'GET':
        try:
            with db.connect() as conn:
                card = conn.execute(text("SELECT * FROM Card WHERE CardID = :cid"), {"cid": card_id}).fetchone()
                list_info = conn.execute(text("SELECT BoardID FROM Lists WHERE ListID = :lid"), {"lid": card.ListID}).fetchone()
                board_id = list_info[0] if list_info else 3
                
                users = conn.execute(text("SELECT UserID, FirstName, LastName FROM Users")).fetchall()
                lists = conn.execute(text("SELECT ListID, Title FROM Lists WHERE BoardID = :bid ORDER BY Position"), {"bid": board_id}).fetchall()
                
                # Get current assignees for highlighting
                assignees_res = conn.execute(text("SELECT UserID FROM Card_Member WHERE CardID = :cid"), {"cid": card_id}).fetchall()
                current_assignee_ids = [row[0] for row in assignees_res]
                
                card_dict = {
                    "CardID": card.CardID, "Title": card.Title, "Description": card.Description, 
                    "Priority": card.Priority, "IsCompleted": card.IsCompleted, 
                    "ListID": card.ListID, "DueDate": card.DueDate, 
                    "AssigneeIDs": current_assignee_ids, "BoardID": board_id
                }
                return render_template('edit_card.html', card=card_dict, users=users, lists=lists)
        except: return redirect(url_for('trello_board'))
    
    elif request.method == 'POST':
        try:
            redirect_board_id = request.form.get('board_id', 3)
            is_completed = True if request.form.get('is_completed') else False
            assignee_ids = request.form.getlist('assignee_ids')
            
            with db.connect() as conn:
                # 1. Update Core Info & Modifier (SP)
                conn.execute(text("CALL SP_Card_Update(:cid, :title, :prio, :done, :uid)"), {
                    "cid": card_id, "title": request.form['title'], 
                    "prio": request.form['priority'], "done": is_completed,
                    "uid": session['user_id']
                })
                
                # 2. Update Extra Info (Move List, Description, Date)
                conn.execute(text("UPDATE Card SET Description = :desc, ListID = :lid, DueDate = :due WHERE CardID = :cid"), 
                             {"desc": request.form['description'], "lid": request.form['list_id'], "due": request.form['due_date'] or None, "cid": card_id})
                
                # 3. Update Assignees (Delete Old -> Insert New)
                conn.execute(text("DELETE FROM Card_Member WHERE CardID = :cid"), {"cid": card_id})
                for uid in assignee_ids:
                    conn.execute(text("INSERT INTO Card_Member (CardID, UserID, Role) VALUES (:cid, :uid, 'Assignee')"), {"cid": card_id, "uid": uid})
                
                conn.commit()
            flash("Card updated successfully!", "success")
            return redirect(url_for('trello_board', board_id=redirect_board_id))
        except Exception as e:
            if "reached its CardLimit" in str(e): flash("⛔ Error: Card count exceeded in list!", "error")
            else: flash(f"Error {e}", "error")
            return redirect(url_for('trello_board'))

@app.route('/delete_card/<int:card_id>', methods=['POST'])
def delete_card(card_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    board_id = request.args.get('board_id', 3)
    try:
        with db.connect() as conn:
            # Call SP with UserID for permission check
            conn.execute(text("CALL SP_Card_Delete(:cid, :uid)"), {"cid": card_id, "uid": session['user_id']})
            conn.commit()
        flash("Card deleted successfully!", "success")
    except Exception as e:
        msg = str(e)
        if "Cannot delete a COMPLETED card" in msg: flash("⛔ Error: Cannot delete a COMPLETED card!", "error")
        elif "ACCESS DENIED" in msg: flash("⛔ Access Denied: You don't have permission to delete this card!", "error")
        else: flash(f"Error {msg}", "error")
    return redirect(url_for('trello_board', board_id=board_id))

@app.route('/create_board', methods=['GET', 'POST'])
def create_board():
    if 'user_id' not in session: return redirect(url_for('login'))
    if request.method == 'GET': return render_template('create_board.html')
    elif request.method == 'POST':
        try:
            with db.connect() as conn:
                # Insert Board
                conn.execute(text("INSERT INTO Board (WorkspaceID, CreatedByUserID, Name, Visibility) VALUES (1, :uid, :name, :vis)"), 
                             {"uid": session['user_id'], "name": request.form['name'], "vis": request.form['visibility']})
                
                new_bid = conn.execute(text("SELECT LAST_INSERT_ID()")).fetchone()[0]
                
                # Create Default Lists
                conn.execute(text("INSERT INTO Lists (BoardID, Title, Position, CardLimit) VALUES (:bid, 'To Do', 1, 0), (:bid, 'Doing', 2, 5), (:bid, 'Done', 3, 0)"), {"bid": new_bid})
                
                # Grant Admin Rights
                conn.execute(text("INSERT INTO Board_Member (BoardID, UserID, Permission) VALUES (:bid, :uid, 'Admin')"), {"bid": new_bid, "uid": session['user_id']})
                conn.commit()
            return redirect(url_for('trello_board', board_id=new_bid))
        except: return redirect(url_for('trello_board'))

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8080, debug=True)