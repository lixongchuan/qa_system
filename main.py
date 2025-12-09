import os
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash
from your_code_here.MongoUtil import MongoUtil
from PIL import Image

app = Flask(__name__)
app.secret_key = 'your_secret_key_here' # 必须设置，用于 Session 加密
app.config['UPLOAD_FOLDER'] = 'static/uploads' # 头像上传路径

mongo = MongoUtil()
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' # 未登录时跳转的页面

# 定义 User 类用于 Flask-Login
class User(UserMixin):
    def __init__(self, user_doc):
        self.id = str(user_doc['_id'])
        self.username = user_doc['username']
        self.email = user_doc['email']
        self.avatar = user_doc.get('avatar', 'default.png')
        self.role = user_doc.get('role', 'user')
    @property
    def is_admin(self):
        return self.role == 'admin'

@login_manager.user_loader
def load_user(user_id):
    user_doc = mongo.get_user_by_id(user_id)
    if user_doc:
        return User(user_doc)
    return None

# ================= 页面路由 =================

@app.route('/')
def index():
    user_stats = {}
    if current_user.is_authenticated:
        mongo.set_current_user(current_user.id)
        # 获取真实统计数据
        user_stats = mongo.get_user_stats(current_user.id)
    else:
        mongo.set_current_user(None)
        
    question_list = mongo.query_question()
    # 把 stats 传给前端
    return render_template('index.html', question_list=question_list, user_stats=user_stats)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user_doc = mongo.get_user_by_email(email)
        
        if user_doc and check_password_hash(user_doc['password_hash'], password):
            user = User(user_doc)
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('邮箱或密码错误')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        username = request.form.get('username')
        password = request.form.get('password')
        
        success, msg = mongo.register_user(email, username, password)
        if success:
            flash('注册成功，请登录')
            return redirect(url_for('login'))
        else:
            flash(msg)
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))


@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        new_username = request.form.get('username')
        new_bio = request.form.get('bio')
        avatar_file = request.files.get('avatar')
        
        filename = current_user.avatar
        
        # === 修改点：移除压缩，改为限制大小 ===
        if avatar_file and avatar_file.filename:
            # 1. 读取文件内容以检查大小
            file_content = avatar_file.read()
            file_size = len(file_content)
            
            # 2. 限制 300KB (300 * 1024 字节)
            if file_size > 300 * 1024:
                flash('图片体积过大 (超过300KB)，请先压缩后再上传')
                # 指针归位，虽然我们要return了，但这是一个好习惯
                avatar_file.seek(0) 
                return redirect(url_for('profile'))
            
            # 3. 如果大小合适，保存文件
            # 重新定位文件指针到开头，因为刚才 read() 读到底了
            avatar_file.seek(0)
            
            # 确保文件名安全，保留原后缀
            ext = os.path.splitext(avatar_file.filename)[1]
            # 使用用户ID+随机数组合文件名，避免缓存问题
            import uuid
            filename = secure_filename(f"{current_user.id}_{uuid.uuid4().hex[:8]}{ext}")
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            
            avatar_file.save(save_path)
            
            # (可选) 删除旧头像代码可以在这里加，节省服务器空间
        
        mongo.update_profile(current_user.id, new_username, new_bio, filename)
        flash('个人资料已更新')
        return redirect(url_for('profile'))
    
    user_info = mongo.get_user_by_id(current_user.id)
    return render_template('profile.html', user=user_info)

@app.route('/question/<question_id>')
def question_detail(question_id):
    if current_user.is_authenticated:
        mongo.set_current_user(current_user.id)
    else:
        mongo.set_current_user(None)

    data = mongo.query_answer(question_id)
    return render_template('answer_list.html', question_answer_dict=data)

# ================= API 路由 =================

@app.route('/post_question', methods=['POST'])
@login_required
def post_question():
    data = request.get_json()
    success, msg = mongo.insert_question(data.get('title'), data.get('detail'), current_user.id)
    if success:
        return jsonify({"status": "success"})
    else:
        return jsonify({"status": "fail", "msg": msg}) # 如果被封禁，返回错误

@app.route('/post_answer', methods=['POST'])
@login_required
def post_answer():
    data = request.get_json()
    success, msg = mongo.insert_answer(data.get('question_id'), data.get('answer'), current_user.id)
    if success:
        return jsonify({"status": "success"})
    else:
        return jsonify({"status": "fail", "msg": msg})

# 3. 新增：删除功能路由
@app.route('/delete_content', methods=['POST'])
@login_required
def delete_content():
    data = request.get_json()
    doc_id = data.get('id')
    doc_type = data.get('type')
    author_id = data.get('author_id')
    
    # 权限检查：要么是管理员，要么是作者本人
    if current_user.is_admin or current_user.id == author_id:
        if mongo.delete_content(doc_id, doc_type):
            return jsonify({"status": "success", "msg": "删除成功"})
    
    return jsonify({"status": "fail", "msg": "无权操作"})

# 4. 新增：管理员专属路由（封禁与置顶）
@app.route('/admin/pin_answer', methods=['POST'])
@login_required
def pin_answer():
    if not current_user.is_admin:
        return jsonify({"status": "fail", "msg": "权限不足"})
    
    data = request.get_json()
    success, is_pinned = mongo.toggle_pin_answer(data.get('answer_id'))
    return jsonify({"status": "success", "is_pinned": is_pinned})

# === 在 main.py 中添加这个路由 ===
@app.route('/admin/pin_question', methods=['POST'])
@login_required
def pin_question():
    if not current_user.is_admin:
        return jsonify({"status": "fail", "msg": "权限不足"})
    
    data = request.get_json()
    success, is_pinned = mongo.toggle_pin_question(data.get('question_id'))
    return jsonify({"status": "success", "is_pinned": is_pinned})

@app.route('/admin/ban_user', methods=['POST'])
@login_required
def ban_user():
    if not current_user.is_admin:
        return jsonify({"status": "fail", "msg": "权限不足"})
    
    data = request.get_json()
    mongo.ban_user(data.get('user_id'), data.get('days'))
    return jsonify({"status": "success", "msg": "用户已封禁"})

@app.route('/vote', methods=['POST'])
@login_required
def vote():
    data = request.get_json()
    # 传入 current_user.id
    success, new_count = mongo.update_vote(
        data.get('doc_id'), 
        data.get('doc_type'), 
        data.get('value'),
        current_user.id
    )
    return jsonify({"status": "success", "new_count": new_count})

@app.route('/u/<user_id>')
def user_public_profile(user_id):
    # 无论是否登录，都可以看别人的主页
    if current_user.is_authenticated:
        mongo.set_current_user(current_user.id)
    else:
        mongo.set_current_user(None)

    data = mongo.get_public_profile(user_id)
    if not data:
        return "用户不存在", 404
        
    return render_template('user_public.html', data=data)

if __name__ == "__main__":
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    app.run(debug=True)