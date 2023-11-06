import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

from datetime import datetime

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# -------------------------------------------------------- INDEX
@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    # Select all stocks
    stocks = db.execute("SELECT * FROM stocks WHERE user_id = ?", session["user_id"])

    # Update stock prices
    for stock in stocks:
        stockquote = lookup(stock["symbol"])
        db.execute("UPDATE stocks SET price = ? WHERE symbol = ?", stockquote["price"], stock["symbol"])

    # Get user's cash
    cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]

    # Get total amount of cash including stocks
    total = cash
    for stock in stocks:
        total += stock["price"] * stock["shares"]

    return render_template("index.html", stocks=stocks, cash=cash, total=total)


# -------------------------------------------------------- BUY
@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        # Add symbol to variable
        symbol = request.form.get("symbol")

        # Look the symbol up
        stockquote = lookup(symbol)

        # If stock symbol not found, it returns None, therefore:
        if not stockquote:
            return apology("Stock symbol not found")

        # If found, change symbol to upper like in the stockquote
        symbol = stockquote["symbol"]

        # Make sure a postive amount of shares is chosen
        while True:
            try:
                shares = int(request.form.get("shares"))
                break
            except:
                # If it is not possible to turn shares into int:
                return apology("Share amount must be a whole postive number")

        if shares < 1:
            return apology("Share amount cannot be negative or zero")

        # Check stocks price
        price = stockquote["price"]
        total = stockquote["price"] * int(shares)

        # Check user's amount of cash
        # The [0]["cash"] makes sure to only take the first value under cash and makes sure it won't be a dict
        cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]

        # If not enough cash
        if total > cash:
            return apology("Not enough cash")

        # Add variable with the time of the transaction
        time = datetime.now()

        # Get name of the company
        # REMEMBER TO USE [""] TO ACCESS THE VALUE
        name = stockquote["name"]

        # Remove cash amount from user
        cashLeft = cash - total
        db.execute("UPDATE users SET cash = ? WHERE id = ?", cashLeft, session["user_id"])

        # Add the stocks to user since they are now bought
        db.execute("INSERT INTO history (name, symbol, shares, price, total, time, user_id) VALUES(?, ?, ?, ?, ?, ?, ?)",
                   name, symbol, shares, price, total, time, session["user_id"])

        # If user already have stocks of same company
        stocks = db.execute("SELECT * FROM stocks WHERE user_id = ?", session["user_id"])
        if not stocks:
            db.execute("INSERT INTO stocks (name, symbol, shares, price, total, user_id) VALUES(?, ?, ?, ?, ?, ?)",
                       name, symbol, shares, price, total, session["user_id"])
        else:
            for stock in stocks:
                if stock["symbol"] == symbol:
                    # shares, price, total
                    # remember to write stock and not stocks
                    newShares = stock["shares"] + int(shares)
                    newTotal = stock["total"] + total
                    db.execute("UPDATE stocks SET shares = ? WHERE symbol = ? AND user_id = ?",
                               newShares, symbol, session["user_id"])
                    db.execute("UPDATE stocks SET price = ? WHERE symbol = ? AND user_id = ?", price, symbol, session["user_id"])
                    db.execute("UPDATE stocks SET total = ? WHERE symbol = ? AND user_id = ?", newTotal, symbol, session["user_id"])

                    # If found return and don't do the rest
                    return redirect("/")

            # If user doesn't have stocks of that company
            db.execute("INSERT INTO stocks (name, symbol, shares, price, total, user_id) VALUES(?, ?, ?, ?, ?, ?)",
                       name, symbol, shares, price, total, session["user_id"])

        # Return to index afterwards
        return redirect("/")

    # First look up the symbol user wanna buy
    else:
        return render_template("buy.html")


# -------------------------------------------------------- HISTORY
@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    # Select all stocks
    history = db.execute("SELECT * FROM history WHERE user_id = ? ORDER BY id DESC", session["user_id"])

    # Update stock prices
    for transaction in history:
        stockquote = lookup(transaction["symbol"])
        db.execute("UPDATE stocks SET price = ? WHERE symbol = ?", stockquote["price"], transaction["symbol"])

    return render_template("history.html", history=history)


# -------------------------------------------------------- LOGIN
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
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

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


# -------------------------------------------------------- LOGOUT
@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


# -------------------------------------------------------- QUOTE
@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    # If search page already open and symbol has been submitted
    if request.method == "POST":
        # Add symbol to variable
        symbol = request.form.get("symbol")

        # Look the symbol up
        stockquote = lookup(symbol)

        # If stock symbol not found, it returns None, therefore:
        if not stockquote:
            return apology("Stock symbol not found")

        # Show table with the found data
        return render_template("quoted.html", stockquote=stockquote)

    # Open search page if it's not already open
    else:
        return render_template("quote.html")


# -------------------------------------------------------- REGISTER
@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    users = db.execute("SELECT * FROM users")

    if request.method == "POST":
        # After submitting registration form
        # CHECK FOR ERRORS
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        # Validate if username is there
        if not username:
            return apology("Must provide username")

        # Validate if password and confirmation are there
        elif not request.form.get("password"):
            return apology("Must provide password")

        elif not request.form.get("confirmation"):
            return apology("Must provide password confirmation")

        # Validate if the passwords are the same
        elif not password == confirmation:
            return apology("Passwords must match")

        # Check if username is already in db
        for user in users:
            if user["username"] == username:
                return apology("Username already taken")

        # Hash the password
        hash = generate_password_hash(password)

        # Insert user to db
        db.execute("INSERT INTO users (username, hash) VALUES(?, ?)", username, hash)

        # Log user in
        for user in users:
            if username == user["username"]:
                session["user_id"] = user["id"]
        return redirect("/")

    else:
        # Display registration form if not already submitted
        return render_template("register.html", users=users)


# -------------------------------------------------------- SELL
@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    # Select all stocks
    stocks = db.execute("SELECT * FROM stocks WHERE user_id = ?", session["user_id"])

    if request.method == "POST":
        # Get symbol and look up to get the current price
        symbol = request.form.get("symbol")
        stockquote = lookup(symbol)

        # If wrong symbol, a symbol not owned or invalid
        if not stockquote:
            return apology("Stock quote not owned")

        # Make symbol upper etc
        symbol = stockquote["symbol"]
        currentStock = db.execute("SELECT * FROM stocks WHERE user_id = ? AND symbol = ?", session["user_id"], symbol)
        if not currentStock:
            return apology("Stock not owned")

        # Make sure a postive amount of shares is chosen
        while True:
            try:
                shares = int(request.form.get("shares"))
                break
            except:
                # If it is not possible to turn shares into int:
                return apology("Share amount must be a whole postive number")

        if shares < 1:
            return apology("Share amount cannot be negative or zero")

        # Make sure amount is no greater than the owned awmound
        elif shares > currentStock[0]["shares"]:
            return apology("Share amount cannot be greater than the amount owned")

        # Get price and total price for all stocks that will be sold
        price = stockquote["price"]
        total = stockquote["price"] * int(shares)

        # Check user's amount of cash
        # The [0]["cash"] makes sure to only take the first value under cash and makes sure it won't be a dict
        cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]

        # Add cash amount to user
        newAmount = cash + total
        db.execute("UPDATE users SET cash = ? WHERE id = ?", newAmount, session["user_id"])

        # Add variable with the time of the transaction
        time = datetime.now()

        # Get name of the company
        # REMEMBER TO USE [""] TO ACCESS THE VALUE
        name = stockquote["name"]

        # Add to history (and make shares negative)
        # -abs() makes a number negative
        db.execute("INSERT INTO history (name, symbol, shares, price, total, time, user_id) VALUES(?, ?, ?, ?, ?, ?, ?)",
                   name, symbol, -abs(int(shares)), price, total, time, session["user_id"])

        # Remove stocks from database
        # If user has exactly selected amount
        if int(shares) == currentStock[0]["shares"]:
            # Remove all stocks from db
            db.execute("DELTE FROM stocks WHERE user_id = ? AND symbol = ?", session["user_id"], symbol)

        # If user has more than selected amount
        else:
            # Remove only selected amount from db
            # shares, price, total
            # Remember [0] to get access to only the value
            newShares = currentStock[0]["shares"] - int(shares)
            newTotal = currentStock[0]["total"] - total
            db.execute("UPDATE stocks SET shares = ? WHERE symbol = ? AND user_id = ?", newShares, symbol, session["user_id"])
            db.execute("UPDATE stocks SET price = ? WHERE symbol = ? AND user_id = ?", price, symbol, session["user_id"])
            db.execute("UPDATE stocks SET total = ? WHERE symbol = ? AND user_id = ?", newTotal, symbol, session["user_id"])

        # Return to index afterwards
        return redirect("/")

    # First show sell form
    else:
        return render_template("sell.html", stocks=stocks)
