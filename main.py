from flask import Flask, render_template, request, jsonify
import os
from utils.config import load_sites_data, save_sites_data
from utils.sites import get_site_by_name, list_site_templates
from utils.post_creator import create_post
from utils.schedules import load_schedules_data, save_schedules_data
from utils.ai_engine import generate_content_with_ai, scrape_url_content
from utils.youtube_service import get_youtube_transcript
from utils.pdf_image_service import extract_text_from_pdf, extract_text_from_image
import shutil

app = Flask(__name__)

@app.route('/')
def index():
    sites = load_sites_data()
    return render_template('index.html', sites=sites)

@app.route('/api/sites', methods=['GET', 'POST'])
def api_sites():
    if request.method == 'POST':
        site_data = request.json
        site_name = site_data.get('name')

        if not site_name:
            return jsonify({'error': 'Site name is required'}), 400

        sites = load_sites_data()
        sites[site_name] = site_data
        save_sites_data(sites)

        # Create site-specific template folder
        site_template_path = os.path.join('static', 'templates', site_name)
        os.makedirs(site_template_path, exist_ok=True)

        return jsonify({'message': 'Site created successfully', 'site': site_data}), 201

    elif request.method == 'GET':
        sites = load_sites_data()
        return jsonify(sites)

@app.route('/api/sites/<name>', methods=['PUT', 'DELETE'])
def api_sites_name(name):
    sites = load_sites_data()
    if request.method == 'PUT':
        site_data = request.json
        if name not in sites:
            return jsonify({'error': 'Site not found'}), 404
        sites[name].update(site_data)
        save_sites_data(sites)
        return jsonify({'message': f'Site {name} updated successfully', 'site': sites[name]}), 200
    elif request.method == 'DELETE':
        if name not in sites:
            return jsonify({'error': 'Site not found'}), 404
        del sites[name]
        save_sites_data(sites)
        # Also remove the site-specific template folder
        site_template_path = os.path.join('static', 'templates', name)
        if os.path.exists(site_template_path):
            import shutil
            shutil.rmtree(site_template_path)
        return jsonify({'message': f'Site {name} deleted successfully'}), 200

@app.route("/load/site/<site_name>")
def load_site_detail(site_name):
    site = get_site_by_name(site_name)
    templates = list_site_templates(site_name)
    return render_template("partials/site_detail.html", site=site, templates=templates)

@app.route('/api/create_post', methods=['POST'])
def api_create_post():
    data = request.json
    site_name = data.get('site_name')
    content_source = data.get('content_source')
    ai_model = data.get('ai_model')
    template = data.get('template')
    source_input = data.get('source_input') # e.g., URL, YouTube URL, PDF/Image file

    if not all([site_name, content_source, ai_model, template, source_input]):
        return jsonify({'error': 'Missing required fields'}), 400

    try:
        # This function will handle the logic of fetching content, generating with AI, and posting
        result = create_post(site_name, content_source, ai_model, template, source_input)
        return jsonify({'message': 'Post creation initiated', 'result': result}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/schedules', methods=['GET', 'POST'])
def api_schedules():
    if request.method == 'POST':
        schedule_data = request.json
        schedules = load_schedules_data()
        schedule_id = str(len(schedules) + 1) # Simple ID generation
        schedules[schedule_id] = schedule_data
        save_schedules_data(schedules)
        return jsonify({'message': 'Schedule created successfully', 'schedule': schedule_data}), 201

    elif request.method == 'GET':
        schedules = load_schedules_data()
        return jsonify(schedules)

@app.route('/api/upload_template', methods=['POST'])
def upload_template():
    if 'template_file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['template_file']
    site_name = request.form.get('site_name')

    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    if not site_name:
        return jsonify({'error': 'Site name is missing'}), 400

    if file and file.filename.endswith('.html'):
        site_template_path = os.path.join('static', 'templates', site_name)
        os.makedirs(site_template_path, exist_ok=True)
        filepath = os.path.join(site_template_path, file.filename)
        file.save(filepath)
        return jsonify({'message': 'Template uploaded successfully'}), 200
    else:
        return jsonify({'error': 'Invalid file type. Only HTML files are allowed.'}), 400

@app.route('/load/schedules')
def load_schedules():
    schedules = load_schedules_data()
    return render_template('partials/schedules.html', schedules=schedules)

@app.route('/api/schedules/<schedule_id>', methods=['PUT', 'DELETE'])
def api_schedules_id(schedule_id):
    schedules = load_schedules_data()
    if request.method == 'PUT':
        schedule_data = request.json
        if schedule_id not in schedules:
            return jsonify({'error': 'Schedule not found'}), 404
        schedules[schedule_id].update(schedule_data)
        save_schedules_data(schedules)
        return jsonify({'message': f'Schedule {schedule_id} updated successfully', 'schedule': schedules[schedule_id]}), 200
    elif request.method == 'DELETE':
        if schedule_id in schedules:
            del schedules[schedule_id]
            save_schedules_data(schedules)
            return jsonify({'message': f'Schedule {schedule_id} deleted successfully'}), 200
        else:
            return jsonify({'error': f'Schedule {schedule_id} not found'}), 404

@app.route('/load/config')
def load_config():
    model_config = load_model_config()
    # In a real application, you would fetch available models from external APIs (OpenRouter/Gemini/etc.)
    # For now, we'll use a dummy list
    available_models = ['ChatGPT', 'Gemini', 'OpenRouter_Model_A', 'OpenRouter_Model_B']
    return render_template('partials/config.html', model_config=model_config, available_models=available_models)

@app.route('/api/config/<site_name>', methods=['POST'])
def api_config(site_name):
    data = request.json
    selected_model = data.get('model')

    if not selected_model:
        return jsonify({'error': 'Model not selected'}), 400

    model_configs = load_model_config()
    model_configs[site_name] = {'model': selected_model}
    save_model_config(model_configs)

    return jsonify({'message': f'Model for {site_name} updated successfully'}), 200

@app.route('/api/ocr/pdf', methods=['POST'])
def api_ocr_pdf():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    if file and file.filename.endswith('.pdf'):
        filepath = os.path.join('uploads', file.filename)
        os.makedirs('uploads', exist_ok=True)
        file.save(filepath)
        extracted_text = extract_text_from_pdf(filepath)
        os.remove(filepath) # Clean up the uploaded file
        if extracted_text:
            return jsonify({'content': extracted_text}), 200
        else:
            return jsonify({'error': 'Failed to extract text from PDF'}), 500
    else:
        return jsonify({'error': 'Invalid file type. Only PDF files are allowed.'}), 400

@app.route('/api/ocr/image', methods=['POST'])
def api_ocr_image():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    if file and file.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
        filepath = os.path.join('uploads', file.filename)
        os.makedirs('uploads', exist_ok=True)
        file.save(filepath)
        extracted_text = extract_text_from_image(filepath)
        os.remove(filepath) # Clean up the uploaded file
        if extracted_text:
            return jsonify({'content': extracted_text}), 200
        else:
            return jsonify({'error': 'Failed to extract text from image'}), 500
    else:
        return jsonify({'error': 'Invalid file type. Only image files are allowed.'}), 400

@app.route('/api/youtube', methods=['POST'])
def api_youtube():
    data = request.json
    youtube_url = data.get('url')
    if not youtube_url:
        return jsonify({'error': 'YouTube URL is required'}), 400

    try:
        # Simple parsing to get video ID
        video_id = youtube_url.split('v=')[-1].split('&')[0]
        transcript = get_youtube_transcript(video_id)
        if transcript:
            return jsonify({'transcript': transcript}), 200
        else:
            return jsonify({'error': 'Failed to get YouTube transcript'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)