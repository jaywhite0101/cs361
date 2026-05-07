from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from recipe_scrapers import scrape_me

app = Flask(__name__)
app.secret_key = 'cs361-secret-key'
# create a local file named recipes.db
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///recipes.db'
db = SQLAlchemy(app)

class Recipe(db.Model):
    id = db.Column(db.Integer, primary_key=True)           # fixed: db.Integer, not db.Model.Integer
    title = db.Column(db.String(200), nullable=False)
    ingredients = db.Column(db.Text, nullable=False)       # stored as newline-separated string
    instructions = db.Column(db.Text, nullable=False)
    source_url = db.Column(db.String(500))                 # fixed: db.String, not db.string
    image_url = db.Column(db.String(500))

# create database file
with app.app_context():
    db.create_all()


# ── Routes ──────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/import')
def import_page():
    return render_template('import.html')


@app.route('/scrape', methods=['POST'])
def scrape_recipe():
    url = request.form.get('url', '').strip()
    if not url:
        flash('Please enter a recipe URL.', 'error')
        return redirect(url_for('import_page'))
    try:
        scraper = scrape_me(url)
        image = None
        try:
            image = scraper.image()
        except Exception:
            pass
        new_recipe = Recipe(
            title=scraper.title(),
            ingredients="\n".join(scraper.ingredients()),
            instructions=scraper.instructions(),
            source_url=url,
            image_url=image
        )
        db.session.add(new_recipe)
        db.session.commit()
        flash(f'"{new_recipe.title}" was imported successfully!', 'success')
        return redirect(url_for('search'))
    except Exception as e:
        flash(f'Could not import recipe: {e}', 'error')
        return redirect(url_for('import_page'))


@app.route('/search')
def search():
    query        = request.args.get('q', '').strip()
    allergens_raw = request.args.get('allergens', '').strip()
    include_raw  = request.args.get('include', '').strip()

    recipes = Recipe.query.all()

    # — text search by title
    if query:
        recipes = [r for r in recipes if query.lower() in r.title.lower()]

    # — allergen exclusion filter (user story: Unlimited Allergen Filter)
    # Any recipe whose ingredient list contains ANY excluded string is hidden.
    allergens = [a.strip().lower() for a in allergens_raw.split(',') if a.strip()]
    if allergens:
        recipes = [
            r for r in recipes
            if not any(allergen in r.ingredients.lower() for allergen in allergens)
        ]

    # — ingredient inclusion filter
    includes = [i.strip().lower() for i in include_raw.split(',') if i.strip()]
    if includes:
        recipes = [
            r for r in recipes
            if all(inc in r.ingredients.lower() for inc in includes)
        ]

    return render_template(
        'search.html',
        recipes=recipes,
        query=query,
        allergens=allergens_raw,
        include=include_raw,
        allergen_list=allergens,
    )


@app.route('/recipe/<int:recipe_id>')
def recipe_detail(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    ingredients_list = [i for i in recipe.ingredients.split('\n') if i.strip()]
    instructions_list = [s.strip() for s in recipe.instructions.split('\n') if s.strip()]
    return render_template(
        'recipe_detail.html',
        recipe=recipe,
        ingredients_list=ingredients_list,
        instructions_list=instructions_list,
    )


@app.route('/recipe/<int:recipe_id>/edit', methods=['GET', 'POST'])
def edit_recipe(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    if request.method == 'POST':
        recipe.title        = request.form.get('title', recipe.title).strip()
        recipe.ingredients  = request.form.get('ingredients', recipe.ingredients)
        recipe.instructions = request.form.get('instructions', recipe.instructions)
        db.session.commit()
        flash('Recipe updated successfully!', 'success')
        return redirect(url_for('recipe_detail', recipe_id=recipe_id))
    return render_template('edit_recipe.html', recipe=recipe)


@app.route('/recipe/<int:recipe_id>/delete', methods=['POST'])
def delete_recipe(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    title = recipe.title
    db.session.delete(recipe)
    db.session.commit()
    flash(f'"{title}" has been deleted. To restore it, re-import it from the original link.', 'info')
    return redirect(url_for('search'))


@app.route('/bulk-import', methods=['POST'])
def bulk_import():
    raw = request.form.get('urls', '')
    urls = [u.strip() for u in raw.splitlines() if u.strip()]
    if not urls:
        flash('No URLs provided.', 'error')
        return redirect(url_for('import_page'))

    success, failed = 0, []
    for url in urls:
        try:
            scraper = scrape_me(url)
            image = None
            try:
                image = scraper.image()
            except Exception:
                pass
            new_recipe = Recipe(
                title=scraper.title(),
                ingredients="\n".join(scraper.ingredients()),
                instructions=scraper.instructions(),
                source_url=url,
                image_url=image
            )
            db.session.add(new_recipe)
            db.session.commit()
            success += 1
        except Exception as e:
            failed.append((url, str(e)))

    if success:
        flash(f'Successfully imported {success} recipe{"s" if success != 1 else ""}!', 'success')
    for url, err in failed:
        flash(f'Failed: {url[:60]}… — {err}', 'error')

    return redirect(url_for('search'))


@app.route('/faq')
def faq():
    return render_template('faq.html')


if __name__ == '__main__':
    app.run(debug=True)
