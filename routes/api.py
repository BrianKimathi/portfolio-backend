from flask import Blueprint, request, jsonify, current_app, send_from_directory
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime, timedelta
import os
import jwt
from models import db, User, Project, ProjectImage

api_bp = Blueprint('api', __name__)

# --- Auth Helpers ---
def generate_token(user_id):
    SECRET_KEY = current_app.config.get('SECRET_KEY', 'your-secret-key-change-this')
    payload = {
        'user_id': user_id,
        'exp': datetime.utcnow() + timedelta(hours=12)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm='HS256')

def verify_token(token):
    SECRET_KEY = current_app.config.get('SECRET_KEY', 'your-secret-key-change-this')
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
        return payload['user_id']
    except Exception:
        return None

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', None)
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Missing or invalid token'}), 401
        token = auth_header.split(' ')[1]
        user_id = verify_token(token)
        if not user_id:
            return jsonify({'error': 'Invalid or expired token'}), 401
        user = User.query.get(user_id)
        if not user or not user.is_admin:
            return jsonify({'error': 'Unauthorized'}), 403
        return f(*args, **kwargs)
    return decorated

def parse_date(date_str):
    if not date_str:
        return None
    if isinstance(date_str, str):
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    return date_str

def parse_bool(val):
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() == 'true'
    return False

# --- Auth Route (login) ---
@api_bp.route('/admin/login', methods=['POST'])
def admin_login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    user = User.query.filter_by(username=username, is_admin=True).first()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({'error': 'Invalid credentials'}), 401
    token = generate_token(user.id)
    return jsonify({'token': token})

@api_bp.route('/admin/create', methods=['POST'])
def create_admin():
    if User.query.filter_by(is_admin=True).first():
        return jsonify({'error': 'Admin user already exists'}), 400
    data = request.json
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    user = User(
        username=username,
        password_hash=generate_password_hash(password),
        is_admin=True
    )
    db.session.add(user)
    db.session.commit()
    return jsonify({'message': 'Admin user created successfully'})

# --- Project CRUD ---
@api_bp.route('/projects', methods=['GET'])
def get_projects():
    projects = Project.query.order_by(Project.order).all()
    return jsonify([{
        'id': p.id,
        'title': p.title,
        'description': p.description,
        'images': [img.url for img in sorted(p.images, key=lambda x: x.order)],
        'github_url': p.github_url,
        'live_url': p.live_url,
        'technologies': p.technologies,
        'featured': p.featured,
        'order': p.order,
        'is_active': p.is_active,
        'created_at': p.created_at.isoformat()
    } for p in projects])

@api_bp.route('/projects/<int:project_id>', methods=['GET'])
def get_project(project_id):
    p = Project.query.get_or_404(project_id)
    return jsonify({
        'id': p.id,
        'title': p.title,
        'description': p.description,
        'images': [img.url for img in sorted(p.images, key=lambda x: x.order)],
        'github_url': p.github_url,
        'live_url': p.live_url,
        'technologies': p.technologies,
        'featured': p.featured,
        'order': p.order,
        'is_active': p.is_active,
        'created_at': p.created_at.isoformat()
    })

@api_bp.route('/projects', methods=['POST'])
@admin_required
def create_project():
    data = request.form
    title = data.get('title')
    description = data.get('description')
    github_url = data.get('github_url')
    live_url = data.get('live_url')
    technologies = data.get('technologies')
    featured = data.get('featured', 'false').lower() == 'true'
    order = int(data.get('order', 0))
    is_active = data.get('is_active', 'true').lower() == 'true'
    # Handle multiple file uploads
    files = request.files.getlist('images')
    if not files or len(files) < 1:
        return jsonify({'error': 'At least one image is required'}), 400
    if len(files) > 6:
        return jsonify({'error': 'Maximum 6 images allowed'}), 400
    project = Project(
        title=title,
        description=description,
        github_url=github_url,
        live_url=live_url,
        technologies=technologies,
        featured=featured,
        order=order,
        is_active=is_active
    )
    db.session.add(project)
    db.session.flush()  # Get project.id before commit
    upload_folder = current_app.config['UPLOAD_FOLDER']
    os.makedirs(upload_folder, exist_ok=True)
    for idx, file in enumerate(files):
        if file and file.filename:
            filename = secure_filename(file.filename)
            timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S%f')
            filename = f"{timestamp}_{idx}_{filename}"
            file.save(os.path.join(upload_folder, filename))
            image_url = f"/api/uploads/{filename}"
            db.session.add(ProjectImage(project_id=project.id, url=image_url, order=idx))
    db.session.commit()
    return jsonify({'message': 'Project created', 'id': project.id}), 201

@api_bp.route('/projects/<int:project_id>', methods=['PUT'])
@admin_required
def update_project(project_id):
    project = Project.query.get_or_404(project_id)
    data = request.form
    project.title = data.get('title', project.title)
    project.description = data.get('description', project.description)
    project.github_url = data.get('github_url', project.github_url)
    project.live_url = data.get('live_url', project.live_url)
    project.technologies = data.get('technologies', project.technologies)
    project.featured = data.get('featured', str(project.featured)).lower() == 'true'
    project.order = int(data.get('order', project.order))
    project.is_active = data.get('is_active', str(project.is_active)).lower() == 'true'
    # Handle multiple file uploads (replace all images if new ones provided)
    files = request.files.getlist('images')
    if files and len(files) > 0:
        if len(files) > 6:
            return jsonify({'error': 'Maximum 6 images allowed'}), 400
        # Remove old images
        ProjectImage.query.filter_by(project_id=project.id).delete()
        upload_folder = current_app.config['UPLOAD_FOLDER']
        os.makedirs(upload_folder, exist_ok=True)
        for idx, file in enumerate(files):
            if file and file.filename:
                filename = secure_filename(file.filename)
                timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S%f')
                filename = f"{timestamp}_{idx}_{filename}"
                file.save(os.path.join(upload_folder, filename))
                image_url = f"/api/uploads/{filename}"
                db.session.add(ProjectImage(project_id=project.id, url=image_url, order=idx))
    db.session.commit()
    return jsonify({'message': 'Project updated'})

@api_bp.route('/projects/<int:project_id>', methods=['DELETE'])
@admin_required
def delete_project(project_id):
    project = Project.query.get_or_404(project_id)
    db.session.delete(project)
    db.session.commit()
    return jsonify({'message': 'Project deleted'})

# --- Serve Uploaded Files ---
@api_bp.route('/uploads/<filename>', methods=['GET'])
def uploaded_file(filename):
    upload_folder = current_app.config['UPLOAD_FOLDER']
    return send_from_directory(upload_folder, filename)

# --- Profile CV Upload ---
@api_bp.route('/profile', methods=['GET', 'PUT'])
def profile():
    from models import Profile
    if request.method == 'GET':
        profile = Profile.query.first()
        if not profile:
            return jsonify({}), 200
        return jsonify({
            'id': profile.id,
            'name': profile.name,
            'title': profile.title,
            'bio': profile.bio,
            'email': profile.email,
            'phone': profile.phone,
            'location': profile.location,
            'github': profile.github,
            'linkedin': profile.linkedin,
            'twitter': profile.twitter,
            'website': profile.website,
            'avatar': profile.avatar,
            'cv_url': profile.cv_url
        })
    # PUT (update)
    data = request.form
    profile = Profile.query.first()
    if not profile:
        profile = Profile()
        db.session.add(profile)
    profile.name = data.get('name', profile.name)
    profile.title = data.get('title', profile.title)
    profile.bio = data.get('bio', profile.bio)
    profile.email = data.get('email', profile.email)
    profile.phone = data.get('phone', profile.phone)
    profile.location = data.get('location', profile.location)
    profile.github = data.get('github', profile.github)
    profile.linkedin = data.get('linkedin', profile.linkedin)
    profile.twitter = data.get('twitter', profile.twitter)
    profile.website = data.get('website', profile.website)
    profile.avatar = data.get('avatar', profile.avatar)
    # Handle CV upload
    if 'cv' in request.files:
        file = request.files['cv']
        if file and file.filename:
            filename = secure_filename(file.filename)
            timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
            filename = f"cv_{timestamp}_{filename}"
            upload_folder = current_app.config['UPLOAD_FOLDER']
            os.makedirs(upload_folder, exist_ok=True)
            file.save(os.path.join(upload_folder, filename))
            profile.cv_url = f"/api/uploads/{filename}"
    db.session.commit()
    return jsonify({'message': 'Profile updated'})

# --- Certification Certificate Upload ---
@api_bp.route('/certifications', methods=['GET', 'POST'])
def certifications():
    from models import Certification
    if request.method == 'GET':
        certs = Certification.query.order_by(Certification.order).all()
        return jsonify([{
            'id': c.id,
            'title': c.title,
            'institution': c.institution,
            'description': c.description,
            'date_awarded': c.date_awarded.isoformat() if c.date_awarded else None,
            'order': c.order,
            'is_active': c.is_active,
            'certificate_url': c.certificate_url
        } for c in certs])
    # POST
    data = request.form
    cert = Certification(
        title=data.get('title'),
        institution=data.get('institution'),
        description=data.get('description'),
        date_awarded=parse_date(data.get('date_awarded')),
        order=data.get('order', 0),
        is_active=parse_bool(data.get('is_active', True))
    )
    # Handle certificate file upload
    if 'certificate' in request.files:
        file = request.files['certificate']
        if file and file.filename:
            filename = secure_filename(file.filename)
            timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
            filename = f"cert_{timestamp}_{filename}"
            upload_folder = current_app.config['UPLOAD_FOLDER']
            os.makedirs(upload_folder, exist_ok=True)
            file.save(os.path.join(upload_folder, filename))
            cert.certificate_url = f"/api/uploads/{filename}"
    db.session.add(cert)
    db.session.commit()
    return jsonify({'message': 'Certification created', 'id': cert.id}), 201

@api_bp.route('/certifications/<int:cert_id>', methods=['PUT'])
@admin_required
def update_certification(cert_id):
    from models import Certification
    cert = Certification.query.get_or_404(cert_id)
    data = request.form
    cert.title = data.get('title', cert.title)
    cert.institution = data.get('institution', cert.institution)
    cert.description = data.get('description', cert.description)
    cert.date_awarded = parse_date(data.get('date_awarded', cert.date_awarded))
    cert.order = data.get('order', cert.order)
    cert.is_active = parse_bool(data.get('is_active', cert.is_active))
    # Handle certificate file upload
    if 'certificate' in request.files:
        file = request.files['certificate']
        if file and file.filename:
            filename = secure_filename(file.filename)
            timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
            filename = f"cert_{timestamp}_{filename}"
            upload_folder = current_app.config['UPLOAD_FOLDER']
            os.makedirs(upload_folder, exist_ok=True)
            file.save(os.path.join(upload_folder, filename))
            cert.certificate_url = f"/api/uploads/{filename}"
    db.session.commit()
    return jsonify({'message': 'Certification updated'})

@api_bp.route('/certifications/<int:cert_id>', methods=['DELETE'])
@admin_required
def delete_certification(cert_id):
    from models import Certification
    cert = Certification.query.get_or_404(cert_id)
    db.session.delete(cert)
    db.session.commit()
    return jsonify({'message': 'Certification deleted'})

# Update stats endpoint
@api_bp.route('/stats', methods=['GET'])
def get_stats():
    from models import Project, Skill, Education, Certification, Contact
    from sqlalchemy import func
    total_projects = Project.query.count()
    total_skills = Skill.query.count()
    total_education = Education.query.count()
    total_certifications = Certification.query.count()
    total_contacts = Contact.query.count()
    project_months = (
        db.session.query(
            func.strftime('%Y-%m', Project.created_at).label('month'),
            func.count(Project.id)
        )
        .group_by('month')
        .order_by('month')
        .all()
    )
    skill_months = (
        db.session.query(
            func.strftime('%Y-%m', Skill.id).label('month'),
            func.count(Skill.id)
        )
        .group_by('month')
        .order_by('month')
        .all()
    )
    return jsonify({
        'total_projects': total_projects,
        'total_skills': total_skills,
        'total_education': total_education,
        'total_certifications': total_certifications,
        'total_contacts': total_contacts,
        'projects_by_month': [ {'month': m, 'count': c} for m, c in project_months ],
        'skills_by_month': [ {'month': m, 'count': c} for m, c in skill_months ],
    })

# --- Skills CRUD ---
@api_bp.route('/skills', methods=['GET'])
def get_skills():
    from models import Skill
    skills = Skill.query.order_by(Skill.order).all()
    return jsonify([{
        'id': s.id,
        'name': s.name,
        'icon': s.icon,
        'proficiency': s.proficiency,
        'category': s.category,
        'order': s.order,
        'is_active': s.is_active
    } for s in skills])

@api_bp.route('/skills', methods=['POST'])
@admin_required
def create_skill():
    from models import Skill
    data = request.json
    skill = Skill(
        name=data.get('name'),
        icon=data.get('icon'),
        proficiency=data.get('proficiency'),
        category=data.get('category'),
        order=data.get('order', 0),
        is_active=data.get('is_active', True)
    )
    db.session.add(skill)
    db.session.commit()
    return jsonify({'message': 'Skill created', 'id': skill.id}), 201

@api_bp.route('/skills/<int:skill_id>', methods=['PUT'])
@admin_required
def update_skill(skill_id):
    from models import Skill
    skill = Skill.query.get_or_404(skill_id)
    data = request.json
    skill.name = data.get('name', skill.name)
    skill.icon = data.get('icon', skill.icon)
    skill.proficiency = data.get('proficiency', skill.proficiency)
    skill.category = data.get('category', skill.category)
    skill.order = data.get('order', skill.order)
    skill.is_active = data.get('is_active', skill.is_active)
    db.session.commit()
    return jsonify({'message': 'Skill updated'})

@api_bp.route('/skills/<int:skill_id>', methods=['DELETE'])
@admin_required
def delete_skill(skill_id):
    from models import Skill
    skill = Skill.query.get_or_404(skill_id)
    db.session.delete(skill)
    db.session.commit()
    return jsonify({'message': 'Skill deleted'})

# --- Experience CRUD ---
@api_bp.route('/experience', methods=['GET'])
def get_experience():
    from models import Experience, Reference
    exp = Experience.query.order_by(Experience.order).all()
    return jsonify([
        {
            'id': e.id,
            'title': e.title,
            'company': e.company,
            'description': e.description,
            'start_date': e.start_date.isoformat() if e.start_date else None,
            'end_date': e.end_date.isoformat() if e.end_date else None,
            'current': e.current,
            'location': e.location,
            'order': e.order,
            'is_active': e.is_active,
            'references': [
                {
                    'id': r.id,
                    'name': r.name,
                    'email': r.email,
                    'phone': r.phone,
                    'note': r.note
                } for r in e.references
            ]
        } for e in exp
    ])

@api_bp.route('/experience/<int:exp_id>/references', methods=['GET'])
def get_references(exp_id):
    from models import Reference
    refs = Reference.query.filter_by(experience_id=exp_id).all()
    return jsonify([
        {
            'id': r.id,
            'name': r.name,
            'email': r.email,
            'phone': r.phone,
            'note': r.note
        } for r in refs
    ])

@api_bp.route('/experience/<int:exp_id>/references', methods=['POST'])
@admin_required
def create_reference(exp_id):
    from models import Reference, db
    data = request.json
    name = data.get('name')
    email = data.get('email')
    phone = data.get('phone')
    note = data.get('note')
    if not name:
        return jsonify({'error': 'Name is required.'}), 400
    ref = Reference(experience_id=exp_id, name=name, email=email, phone=phone, note=note)
    db.session.add(ref)
    db.session.commit()
    return jsonify({'message': 'Reference added.', 'id': ref.id}), 201

@api_bp.route('/references/<int:ref_id>', methods=['PUT'])
@admin_required
def update_reference(ref_id):
    from models import Reference, db
    ref = Reference.query.get_or_404(ref_id)
    data = request.json
    ref.name = data.get('name', ref.name)
    ref.email = data.get('email', ref.email)
    ref.phone = data.get('phone', ref.phone)
    ref.note = data.get('note', ref.note)
    db.session.commit()
    return jsonify({'message': 'Reference updated.'})

@api_bp.route('/references/<int:ref_id>', methods=['DELETE'])
@admin_required
def delete_reference(ref_id):
    from models import Reference, db
    ref = Reference.query.get_or_404(ref_id)
    db.session.delete(ref)
    db.session.commit()
    return jsonify({'message': 'Reference deleted.'})

# --- Education CRUD ---
@api_bp.route('/education', methods=['GET'])
def get_education():
    from models import Education
    edu = Education.query.order_by(Education.order).all()
    return jsonify([{
        'id': e.id,
        'degree': e.degree,
        'institution': e.institution,
        'description': e.description,
        'start_date': e.start_date.isoformat() if e.start_date else None,
        'end_date': e.end_date.isoformat() if e.end_date else None,
        'current': e.current,
        'gpa': e.gpa,
        'order': e.order,
        'is_active': e.is_active
    } for e in edu])

@api_bp.route('/education', methods=['POST'])
@admin_required
def create_education():
    from models import Education
    data = request.json
    edu = Education(
        degree=data.get('degree'),
        institution=data.get('institution'),
        description=data.get('description'),
        start_date=parse_date(data.get('start_date')),
        end_date=parse_date(data.get('end_date')),
        current=parse_bool(data.get('current', False)),
        gpa=data.get('gpa'),
        order=data.get('order', 0),
        is_active=parse_bool(data.get('is_active', True))
    )
    db.session.add(edu)
    db.session.commit()
    return jsonify({'message': 'Education created', 'id': edu.id}), 201

@api_bp.route('/education/<int:edu_id>', methods=['PUT'])
@admin_required
def update_education(edu_id):
    from models import Education
    edu = Education.query.get_or_404(edu_id)
    data = request.json
    edu.degree = data.get('degree', edu.degree)
    edu.institution = data.get('institution', edu.institution)
    edu.description = data.get('description', edu.description)
    edu.start_date = parse_date(data.get('start_date', edu.start_date))
    edu.end_date = parse_date(data.get('end_date', edu.end_date))
    edu.current = parse_bool(data.get('current', edu.current))
    edu.gpa = data.get('gpa', edu.gpa)
    edu.order = data.get('order', edu.order)
    edu.is_active = parse_bool(data.get('is_active', edu.is_active))
    db.session.commit()
    return jsonify({'message': 'Education updated'})

@api_bp.route('/education/<int:edu_id>', methods=['DELETE'])
@admin_required
def delete_education(edu_id):
    from models import Education
    edu = Education.query.get_or_404(edu_id)
    db.session.delete(edu)
    db.session.commit()
    return jsonify({'message': 'Education deleted'})

# --- Contacts ---
@api_bp.route('/contacts', methods=['GET'])
def get_contacts():
    from models import Contact
    contacts = Contact.query.order_by(Contact.created_at.desc()).all()
    return jsonify([{
        'id': c.id,
        'name': c.name,
        'email': c.email,
        'message': c.message,
        'created_at': c.created_at.isoformat() if c.created_at else None,
        'read': c.read
    } for c in contacts])

@api_bp.route('/contacts', methods=['POST'])
def create_contact():
    from models import Contact, db
    data = request.json
    name = data.get('name')
    email = data.get('email')
    message = data.get('message')
    if not name or not email or not message:
        return jsonify({'error': 'All fields are required.'}), 400
    contact = Contact(name=name, email=email, message=message)
    db.session.add(contact)
    db.session.commit()
    return jsonify({'message': 'Contact message received.'}), 201

@api_bp.route('/contacts/<int:contact_id>', methods=['PUT'])
@admin_required
def mark_contact_read(contact_id):
    from models import Contact
    contact = Contact.query.get_or_404(contact_id)
    contact.read = True
    db.session.commit()
    return jsonify({'message': 'Contact marked as read'})

@api_bp.route('/contacts/<int:contact_id>', methods=['DELETE'])
@admin_required
def delete_contact(contact_id):
    from models import Contact
    contact = Contact.query.get_or_404(contact_id)
    db.session.delete(contact)
    db.session.commit()
    return jsonify({'message': 'Contact deleted'}) 

@api_bp.route('/experience', methods=['POST'])
@admin_required
def create_experience():
    from models import Experience, db
    data = request.json
    exp = Experience(
        title=data.get('title'),
        company=data.get('company'),
        description=data.get('description'),
        start_date=parse_date(data.get('start_date')),
        end_date=parse_date(data.get('end_date')),
        current=parse_bool(data.get('current', False)),
        location=data.get('location'),
        order=data.get('order', 0),
        is_active=parse_bool(data.get('is_active', True))
    )
    db.session.add(exp)
    db.session.commit()
    return jsonify({'message': 'Experience created', 'id': exp.id}), 201 