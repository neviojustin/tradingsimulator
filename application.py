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
    user_id = session["user_id"]
    total_worth = db.execute("SELECT cash FROM users WHERE id =:user_id", user_id = user_id)[0]["cash"]
    balance = usd(total_worth)
    holdings = db.execute("SELECT SUM(amount), stock_name, stock_symbol FROM (SELECT * FROM transactions WHERE user_id=:user_id) GROUP BY stock_symbol", user_id=user_id)
    for holding in holdings:
        holding["price"] = (lookup(holding["stock_symbol"]))["price"]
        holding["stock_symbol"] = str.upper(holding["stock_symbol"])
        holding["stock_total"] = holding["price"] * holding["SUM(amount)"]
        total_worth += holding["stock_total"]
        holding["stock_total"] = usd(holding["stock_total"])
        holding["price"] = usd(holding["price"])

    return render_template('index.html', holdings=holdings, balance=balance, grand_total=usd(total_worth))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    if request.method == "GET":
        return render_template("buy.html")
    else:
        print(request.form.get("reply"))
        if request.form.get("reply") == None:
            if not request.form.get("symbol"):
                return apology("No Symbol")
            if not request.form.get("shares"):
                return apology("Share amount is not a positive integer")
            symbol = request.form.get("symbol")
            amount = int(request.form.get("shares"))
            user_id = session["user_id"]

            if lookup(symbol) == None:
                return apology("Invalid Share")

            price = lookup(symbol)["price"]
            stockname = lookup(symbol)["name"]

            balance = db.execute("SELECT cash FROM users WHERE id =:user_id", user_id = user_id)[0]["cash"]

            total_order = price * amount
            session["symbol"] = symbol
            session["amount"] = amount
            session["price"] = price
            session["stockname"] = stockname
            session["balance"] = balance
            session["total_order"] = total_order


            if balance < (total_order):
                return apology("Insufficient balance")

            return render_template("buyconfirmation.html", stockname=stockname, price=usd(price), amount=amount, symbol=str.upper(symbol), total=usd(total_order))
        elif request.form.get("reply") == 'Cancel':
            session.pop("symbol")
            session.pop("amount")
            session.pop("price")
            session.pop("stockname")
            session.pop("balance")
            session.pop("total_order")
            flash("Cancelled Order")
            return render_template("buy.html")

        elif request.form.get("reply") == 'Proceed':
            symbol = session["symbol"]
            amount = session["amount"]
            price = session["price"]
            stockname = session["stockname"]
            balance = session["balance"]
            total_order = session["total_order"]

            user_id = session["user_id"]

            print(session)
            #Make a transaction (Update into transactions table)
            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            db.execute("INSERT INTO transactions (user_id, datetime, stock_name, stock_symbol, then_price, amount) VALUES (:user_id, :datetime, :stock_name, :stock_symbol, :then_price, :amount)", user_id=user_id, datetime=current_time, stock_name=stockname, stock_symbol=symbol, then_price=price, amount=amount)

            new_balance = balance - (total_order)
            #Deduct balance
            db.execute("UPDATE users SET cash =:new_balance WHERE id =:user_id", new_balance=new_balance , user_id=user_id)

            session.pop("symbol")
            session.pop("amount")
            session.pop("price")
            session.pop("stockname")
            session.pop("balance")
            session.pop("total_order")
            #Alerts user of success
            flash(f"Bought {amount}x {str.upper(symbol)} share successfully")

            print("AFTER", session)
            return redirect('/')
        else:
            return apology("ERROR in buy")


@app.route("/history")
@login_required
def history():
    user_id = session["user_id"]
    history = db.execute("SELECT stock_symbol, then_price, amount, datetime FROM transactions WHERE user_id=:user_id ORDER BY datetime", user_id=user_id)
    for transaction in history:
        transaction["stock_symbol"] = str.upper(transaction["stock_symbol"])
        transaction["then_price"] = usd(transaction["then_price"])
    return render_template("history.html", transaction_history=history)


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
        if len(rows) != 1:
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        #alerts login
        flash("Successfully logged in!")

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
    if request.method == "GET":
        return render_template("quote.html")

    #POST Request
    else:
        symbol = request.form.get("symbol")
        result = lookup(symbol)
        if result == None:
            return apology("Invalid Stock")
        name = result["name"]
        price = usd(result["price"])
        symbol = result["symbol"]

        return render_template("quoted.html", name=name, price=price, symbol=symbol)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")
    else:
    # Ensure username was submitted
        userlist= []
        for user in db.execute("SELECT username FROM users;"):
            userlist.append(user["username"])
        if not request.form.get("username"):
            return apology("must provide username", 403)

        elif (request.form.get("username")) in userlist:
            return apology("Username already taken!")

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Ensure password was reconfirmed
        elif not request.form.get("password-confirm"):
            return apology("must reconfirm password", 403)

        if request.form.get("password") != request.form.get("password-confirm"):
            return apology("Passwords don't match!")


        else:
            username = request.form.get("username")
            passhash= generate_password_hash(request.form.get("password"))
            db.execute("INSERT INTO users (username, hash) VALUES (:username, :passhash)", username=username, passhash=passhash)
            return redirect("/login")




@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    if request.method == "GET":
        user_id = session["user_id"]
        stocklist = db.execute("SELECT stock_symbol FROM (SELECT * FROM transactions WHERE user_id=:user_id) GROUP BY stock_symbol HAVING SUM(amount) > 0", user_id=user_id)
        for stock in stocklist:
            stock["stock_symbol"] = str.upper(stock["stock_symbol"])
        return render_template("sell.html", stocklist=stocklist)
    else:
        if request.form.get("reply") == None:
            if not request.form.get("symbol"):
                return apology("No Symbol")
            if not request.form.get("shares"):
                return apology("Share amount is not a positive integer")
            symbol = request.form.get("symbol")
            symbol_lower = str.lower(symbol)
            amount = int(request.form.get("shares"))
            amount_deduct = amount * -1
            user_id = session["user_id"]
            stock_count = db.execute("SELECT SUM(amount) FROM (SELECT * FROM transactions WHERE user_id= :user_id) GROUP BY stock_symbol HAVING stock_symbol = :symbol", user_id=user_id, symbol=symbol_lower)[0]["SUM(amount)"]

            if lookup(symbol) == None:
                return apology("Invalid Share")

            price = lookup(symbol)["price"]
            stockname = lookup(symbol)["name"]

            balance = db.execute("SELECT cash FROM users WHERE id =:user_id", user_id = user_id)[0]["cash"]

            print(price, balance)
            if stock_count < amount:
                return apology("Insufficient Shares")
            total_order = price*amount

            session["symbol"] = symbol
            session["symbol_lower"] = symbol_lower
            session["amount"] = amount
            session["amount_deduct"] = amount_deduct
            session["price"] = price
            session["stockname"] = stockname
            session["balance"] = balance
            session["stock_count"] = stock_count

            return render_template("sellconfirmation.html", stockname=stockname, price=usd(price), amount=amount, symbol=str.upper(symbol), total=usd(total_order))

        elif request.form.get("reply") == 'Cancel':
            session.pop("symbol")
            session.pop("symbol_lower")
            session.pop("amount")
            session.pop("amount_deduct")
            session.pop("price")
            session.pop("stockname")
            session.pop("balance")
            session.pop("stock_count")

            flash("Cancelling sale")
            return render_template("sell.html")

        elif request.form.get("reply") == 'Proceed':

            symbol = session["symbol"]
            symbol_lower = session["symbol_lower"]
            amount = session["amount"]
            amount_deduct = session["amount_deduct"]
            price = session["price"]
            stockname = session["stockname"]
            balance = session["balance"]
            stock_count = session["stock_count"]

            user_id = session["user_id"]

            #Make a transaction (Update into transactions tabke)
            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            db.execute("INSERT INTO transactions (user_id, datetime, stock_name, stock_symbol, then_price, amount) VALUES (:user_id, :datetime, :stock_name, :stock_symbol, :then_price, :amount)", user_id=user_id, datetime=current_time, stock_name=stockname, stock_symbol=symbol_lower, then_price=price, amount=amount_deduct)

            new_balance = balance + (price*amount)
            #Deduct balance
            db.execute("UPDATE users SET cash =:new_balance WHERE id =:user_id", new_balance=new_balance , user_id=user_id)

            #Alerts user for successfully sold
            flash(f"Sold {amount}x {str.upper(symbol)} share successfully")

            session.pop("symbol")
            session.pop("symbol_lower")
            session.pop("amount")
            session.pop("amount_deduct")
            session.pop("price")
            session.pop("stockname")
            session.pop("balance")
            session.pop("stock_count")

            return redirect("/")
        else:
            return apology("ERROR in sell")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
