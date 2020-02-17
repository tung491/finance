import os
import datetime

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    user_id = session['user_id']
    """Show portfolio of stocks"""
    data = db.execute("SELECT symbol, company_name, shares "
                      "from transactions where user_id = :user_id "
                      "group by symbol;", user_id=session['user_id'])
    for row in data:
        symbol = row['symbol']
        row['price'] = lookup(symbol)['price']
        row['total'] = usd(row['shares'] * row['price'])
    cash = usd(db.execute("SELECT cash from users where id = :id", id=user_id)[0]['cash'])
    data.append({'symbol': 'CASH', 'total': cash})
    return render_template("index.html", data=data)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    user_id = session['user_id']
    if request.method == "GET":
        return render_template('buy.html')
    else:
        symbol = request.form.get('symbol')
        shares = request.form.get('shares')
        if not symbol:
            apology('must provide symbol')
        if not shares:
            apology('must provide shares')
        shares = int(shares)
        if shares <= 0:
            apology('Invaild shares')
        data = lookup(symbol)

        if data:
            name = data['name']
            price = data['price']
            total = price * shares
            cash = db.execute("SELECT cash from users where id = :id", id=user_id)[0]['cash']
            if cash > total:
                cash -= total
                db.execute("UPDATE users SET cash = :cash "
                           "where id = :id", cash=cash, id=user_id)
                db.execute("INSERT INTO transactions(symbol, company_name, shares, price, total, user_id, transaction_time) "
                           "VALUES (:symbol, :company_name , :shares, :price, :total, :user_id, :transaction_time)",
                           symbol=symbol, company_name=name, shares=shares, price=price, total=total, user_id=user_id,
                           transaction_time=datetime.datetime.now())
                redirect('/index')
            else:
                apology("don't have enough money")
        else:
            apology('symbol is not found')


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    user_id = session['user_id']
    data = db.execute('SELECT symbol, company_name, shares, total, transaction_time from transactions where user_id = :user_id;',
                      user_id=user_id)
    return render_template('history.html', data=data)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == 'GET':
        return render_template('quote.html')
    else:
        symbol = request.form.get('symbol')
        if not symbol:
            apology('must provide symbol')
        data = lookup(symbol)
        if data:
            name = data['name']
            price = data['price']
            return render_template('quote_result.html', name=name, price=price, symbol=symbol)
        else:
            apology('symbol is not found')



@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == 'GET':
        return render_template('register.html')
    else:
        username = request.form.get('username')
        password = request.form.get('password')
        confirmation = request.form.get('confirmation')
        if not username:
            return apology("must provide username", 403)
        if not password:
            return apology("must provide password", 403)
        if not confirmation:
            return apology("must provide confirmation", 403)
        if password != confirmation:
            return apology("confirmation is not match", 403)
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=username)
        if len(rows) != 0:
            return apology("username is already exist")
        hash_password = generate_password_hash(password)
        db.execute("INSERT INTO users(username, hash, cash) "
                   "VALUES (:username, :hash, 10000)", username=username, hash=hash_password)
        return redirect('/login')


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    user_id = session['user_id']
    symbols = db.execute('SELECT symbol from transactions'
                         ' where user_id=:user_id group by symbol', user_id=user_id)
    symbols = [row['symbol'] for row in symbols]
    if request.method == 'GET':
        return render_template('sell.html', symbols=symbols)
    else:
        symbol = request.form.get('symbol')
        sell_shares = request.form.get('shares')
        data = db.execute("SELECT company_name, sum(shares) as shares "
                                    "from transactions where user_id= :user_id "
                                    "and symbol= :symbol group by symbol",
                                    user_id=user_id, symbol=symbol)[0]
        current_shares = data['shares']
        name = data['company_name']
        if not sell_shares:
            apology('Invaid Shares')
        sell_shares = int(sell_shares)
        if sell_shares <= 0:
            apology('Invaild shares')
        if sell_shares > current_shares:
            apology("You don't have enough shares")
        price = lookup(symbol)['price']
        total = price * sell_shares
        cash = db.execute("SELECT cash from users where id = :id", id=user_id)[0]['cash']
        cash += total
        db.execute("UPDATE users SET cash = :cash "
                   "where id = :id", cash=cash, id=user_id)
        db.execute("INSERT INTO transactions(symbol, company_name, shares, price, total, user_id, transaction_time) "
                    "VALUES (:symbol, :company_name , :shares, :price, :total, :user_id, :transaction_time)",
                    symbol=symbol, company_name=name, shares=sell_shares, price=price, total=-total, user_id=user_id,
                   transaction_time=datetime.datetime.now())
        return redirect('/')


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
