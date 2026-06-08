import base64
import io
import re
import uuid

from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from recipe_scrapers import scrape_me

import microservices as ms

app = Flask(__name__)
app.secret_key = 'cs361-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///recipes.db'
db = SQLAlchemy(app)

class Recipe(db.Model):
    id           = db.Column(db.Integer,     primary_key=True)
    title        = db.Column(db.String(200), nullable=False)
    ingredients  = db.Column(db.Text,        nullable=False)
    instructions = db.Column(db.Text,        nullable=False)
    source_url   = db.Column(db.String(500))
    image_url    = db.Column(db.String(500))

with app.app_context():
    db.create_all()


# session user ID (used by note-taking microservice)

@app.before_request
def ensure_user_id():
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())


# ingredient scaling helper
# parses the leading number from an ingredient string, calls the unit conversion microservice to scale it, then rebuilds the string

QUANTITY_RE = re.compile(r'^(\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?)')

def _scale_ingredient_string(text: str, scale_factor: float) -> str:
    m = QUANTITY_RE.match(text.strip())
    if not m:
        return text  # no numeric quantity found (such as "salt to taste")

    raw  = m.group(1).strip()
    rest = text[m.end():]

    if ' ' in raw:                           # mixed number: "1 1/2"
        whole_s, frac_s = raw.split(maxsplit=1)
        num, den = frac_s.split('/')
        qty = float(whole_s) + float(num) / float(den)
    elif '/' in raw:                          # simple fraction: "1/2"
        num, den = raw.split('/')
        qty = float(num) / float(den)
    else:
        qty = float(raw)

    result = ms.scale_value(qty, scale_factor)
    if result['status'] != 'success':
        return text

    scaled = result['result']
    formatted = str(int(scaled)) if scaled == int(scaled) else f"{scaled:.3g}"
    return formatted + rest


# routes

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
    query         = request.args.get('q',         '').strip()
    allergens_raw = request.args.get('allergens', '').strip()
    include_raw   = request.args.get('include',   '').strip()
    sort_param    = request.args.get('sort',       '')

    recipes = Recipe.query.all()

    if query:
        recipes = [r for r in recipes if query.lower() in r.title.lower()]

    allergens = [a.strip().lower() for a in allergens_raw.split(',') if a.strip()]
    if allergens:
        recipes = [
            r for r in recipes
            if not any(allergen in r.ingredients.lower() for allergen in allergens)
        ]

    includes = [i.strip().lower() for i in include_raw.split(',') if i.strip()]
    if includes:
        recipes = [
            r for r in recipes
            if all(inc in r.ingredients.lower() for inc in includes)
        ]

    # sorting microservice
    if sort_param and recipes:
        parts      = sort_param.split('-', 1)
        sort_key   = parts[0]
        sort_order = parts[1] if len(parts) == 2 else 'ASC'

        recipe_dicts = [{"id": r.id, "title": r.title} for r in recipes]
        result       = ms.sort_recipes(recipe_dicts, sort_key, sort_order)

        if result['status'] == 'success':
            id_order = [d['id'] for d in result['sorted_data']]
            id_index = {rid: i for i, rid in enumerate(id_order)}
            recipes  = sorted(recipes, key=lambda r: id_index.get(r.id, 999))
        else:
            flash(f'Sorting unavailable: {result["message"]}', 'info')

    return render_template(
        'search.html',
        recipes=recipes,
        query=query,
        allergens=allergens_raw,
        include=include_raw,
        allergen_list=allergens,
        sort_param=sort_param,
    )


@app.route('/recipe/<int:recipe_id>')
def recipe_detail(recipe_id):
    recipe            = Recipe.query.get_or_404(recipe_id)
    ingredients_list  = [i for i in recipe.ingredients.split('\n') if i.strip()]
    instructions_list = [s.strip() for s in recipe.instructions.split('\n') if s.strip()]

    # load saved note from note-taking microservice
    saved_note = ''
    note_result = ms.load_note(session['user_id'], f'recipe_{recipe_id}')
    if note_result['status'] == 'success':
        saved_note = note_result['note']

    return render_template(
        'recipe_detail.html',
        recipe=recipe,
        ingredients_list=ingredients_list,
        instructions_list=instructions_list,
        saved_note=saved_note,
    )


@app.route('/recipe/<int:recipe_id>/edit', methods=['GET', 'POST'])
def edit_recipe(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    if request.method == 'POST':
        recipe.title        = request.form.get('title',        recipe.title).strip()
        recipe.ingredients  = request.form.get('ingredients',  recipe.ingredients)
        recipe.instructions = request.form.get('instructions', recipe.instructions)
        db.session.commit()
        flash('Recipe updated successfully!', 'success')
        return redirect(url_for('recipe_detail', recipe_id=recipe_id))
    return render_template('edit_recipe.html', recipe=recipe)


@app.route('/recipe/<int:recipe_id>/delete', methods=['POST'])
def delete_recipe(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    title  = recipe.title
    db.session.delete(recipe)
    db.session.commit()
    # also clean up any saved note for this recipe
    ms.delete_note(session['user_id'], f'recipe_{recipe_id}')
    flash(f'"{title}" has been deleted. To restore it, re-import it from the original link.', 'info')
    return redirect(url_for('search'))


@app.route('/bulk-import', methods=['POST'])
def bulk_import():
    raw  = request.form.get('urls', '')
    urls = [u.strip() for u in raw.splitlines() if u.strip()]
    if not urls:
        flash('No URLs provided.', 'error')
        return redirect(url_for('import_page'))

    success, failed = 0, []
    for url in urls:
        try:
            scraper = scrape_me(url)
            image   = None
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


# microservice API endpoints (called w/ fetch from the browser)

@app.route('/recipe/<int:recipe_id>/scale', methods=['POST'])
def scale_recipe(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    data   = request.get_json()

    try:
        scale_factor = float(data.get('scale_factor', 1.0))
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "scale_factor must be a number."}), 400

    ingredients_list = [i for i in recipe.ingredients.split('\n') if i.strip()]
    scaled = [_scale_ingredient_string(ing, scale_factor) for ing in ingredients_list]

    return jsonify({"status": "success", "scaled_ingredients": scaled})


@app.route('/recipe/<int:recipe_id>/export')
def export_recipe(recipe_id):
    recipe            = Recipe.query.get_or_404(recipe_id)
    fmt               = request.args.get('format', 'pdf').lower()
    ingredients_list  = [i for i in recipe.ingredients.split('\n') if i.strip()]
    instructions_list = [s.strip() for s in recipe.instructions.split('\n') if s.strip()]

    result = ms.export_recipe(recipe.title, ingredients_list, instructions_list, fmt)

    if result['status'] != 'success':
        flash(f'Export failed: {result["message"]}', 'error')
        return redirect(url_for('recipe_detail', recipe_id=recipe_id))

    if fmt == 'pdf':
        pdf_bytes = base64.b64decode(result['pdf_bytes'])
        safe_name = re.sub(r'[^\w\s-]', '', recipe.title).strip().replace(' ', '_')
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"{safe_name}.pdf"
        )

    # markdown / plain — return as JSON for the browser to handle
    return jsonify(result)


@app.route('/recipe/<int:recipe_id>/note', methods=['POST'])
def save_note(recipe_id):
    data   = request.get_json()
    note   = data.get('note', '')
    result = ms.save_note(session['user_id'], f'recipe_{recipe_id}', note)
    return jsonify(result)


@app.route('/recipe/<int:recipe_id>/note/delete', methods=['POST'])
def delete_note(recipe_id):
    result = ms.delete_note(session['user_id'], f'recipe_{recipe_id}')
    return jsonify(result)


@app.route('/faq')
def faq():
    return render_template('faq.html')


if __name__ == '__main__':
    app.run(debug=True)