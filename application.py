import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
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
    grandtotal = 0
    rows = db.execute("""SELECT symbol, SUM(shares) as TotalShares
            FROM mainpage
            WHERE user_id=:user_id
            GROUP BY symbol
            HAVING TotalShares > 0;""",
                      user_id=session["user_id"])

    data = []
    for row in rows:
        stock = lookup(row["symbol"])
        data.append({
            "symbol": stock["symbol"],
            "name": stock["name"],
            "shares": row["TotalShares"],
            "price": usd(stock["price"]),
            "total": usd(stock["price"] * row["TotalShares"])
        })
        grandtotal += stock["price"] * row["TotalShares"]

    rows = db.execute("SELECT cash FROM users WHERE id=:user_id", user_id=session["user_id"])
    cash = rows[0]["cash"]

    grandtotal += cash

    return render_template("index.html", data=data, cash=usd(cash), grandtotal=usd(grandtotal))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    if request.method == "POST":
        if not request.form.get("symbol"):
            return apology("please enter stock", 400)
        if not request.form.get("shares"):
            return apology("specify no. of shares", 400)
        kk = request.form.get("symbol").upper()
        yes = lookup(kk)
        shares = int(request.form.get("shares"))
        if yes is None:
            return apology("No such stock exists", 400)
        rows = db.execute("SELECT cash FROM users WHERE id=:id", id=session['user_id'])
        cash = rows[0]["cash"]

        updated = cash - (shares * yes['price'])
        if updated < 0:
            return apology("Sorry son, Ya broke", 400)
        db.execute("UPDATE users SET cash=:updated WHERE id=:id",
                   updated=updated,
                   id=session['user_id'])

        db.execute("""INSERT INTO mainpage
                        (user_id, symbol, shares , price)
                    VALUES (:user_id, :symbol, :shares , :price)""",
                   user_id=session["user_id"],
                   symbol=yes["symbol"],
                   shares=shares,
                    price=yes["price"])
        flash("Bought!")
        return redirect("/")
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    tran = db.execute("""SELECT symbol, shares, price, transacted
                        FROM mainpage WHERE user_id=:user_id;
                        """, user_id=session["user_id"])
    for i in range(len(tran)):
        tran[i]['price'] = usd(tran[i]['price'])
    return render_template("history.html", transactions=tran)


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
    if request.method == "POST":
        if not request.form.get("symbol"):
            return apology("must provide stock symbol", 400)
        s = request.form.get("symbol").upper()
        stock = lookup(s)

        if stock is None:
            return apology("No such stock exists", 400)
        return render_template("quoted.html", stockName={
            'name': stock['name'],
            'symbol': stock['symbol'],
            'price': usd(stock['price'])
        })
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        elif not request.form.get("confirmation"):
            return apology("must confirm password", 400)

        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("Password and Confirmation must match", 400)

        try:
            primarykey = db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)",
                                    username=request.form.get("username"),
                                    hash=generate_password_hash(request.form.get("password")))

        except:
            return apology("username exists", 400)

        if primarykey is None:
            return apology("registration error", 403)
        session["user_id"] = primarykey

        return redirect("/")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    if request.method == "POST":
        if not request.form.get("symbol"):
            return apology("please enter stock", 403)
        if not request.form.get("shares"):
            return apology("specify no. of shares", 403)
        kk = request.form.get("symbol").upper()
        yes = lookup(kk)
        shares = int(request.form.get("shares"))
        if yes is None:
            return apology("No such stock exists", 400)

        rows = db.execute("""SELECT symbol, SUM(shares) as TotalShares
                        FROM mainpage
                        WHERE user_id=:user_id
                        GROUP BY symbol
                        HAVING TotalShares > 0;
                    """, user_id=session['user_id'])
        for row in rows:
            if row["symbol"] == kk:
                if shares > row["TotalShares"]:
                    return apology("you don't have that many shares")

        rows = db.execute("SELECT cash FROM users WHERE id=:id", id=session['user_id'])
        cash = rows[0]["cash"]

        updated = cash + (shares * yes['price'])
        if updated < 0:
            return apology("Sorry son, Ya broke", 403)
        db.execute("UPDATE users SET cash=:updated WHERE id=:id",
                   updated=updated,
                   id=session['user_id'])

        db.execute("""INSERT INTO mainpage
                        (user_id, symbol, shares , price)
                    VALUES (:user_id, :symbol, :shares , :price)""",
                   user_id=session["user_id"],
                   symbol=yes["symbol"],
                   shares=-1 * shares,
                   price=yes["price"])

        flash("Sold!")
        return redirect("/")
    else:
        rows = db.execute("""SELECT symbol
                            FROM mainpage
                            WHERE user_id=:user_id
                            GROUP BY symbol
                            HAVING SUM(shares) > 0;
                            """, user_id=session["user_id"])
        return render_template("sell.html", symbols=[row["symbol"] for row in rows])



def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
