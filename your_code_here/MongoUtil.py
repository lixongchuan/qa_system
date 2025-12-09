import pymongo
from bson import ObjectId
import datetime
from werkzeug.security import generate_password_hash

class MongoUtil(object):
    def __init__(self):
        # 保持你的数据库连接不变
        self.client = pymongo.MongoClient("mongodb://lixongchuan:lichuan430@117.72.52.104:27017/")
        self.db = self.client["qa_system"]
        self.db.users.create_index("email", unique=True)
        self.current_user_id = None
        
        # === 新增：初始化管理员账号 ===
        self._init_admin()

    def _init_admin(self):
        """初始化或修复管理员账号"""
        admin_email = "admin@quest.bupang.xyz"
        user = self.db.users.find_one({"email": admin_email})
        
        if not user:
            # 如果不存在，创建它
            print("正在初始化管理员账号...")
            admin_data = {
                "email": admin_email,
                "username": "管理员",
                "password_hash": generate_password_hash("admin"),
                "avatar": "default.png", 
                "bio": "系统管理员，维护社区秩序",
                "role": "admin", 
                "created_at": datetime.datetime.now()
            }
            self.db.users.insert_one(admin_data)
        else:
            # === 新增逻辑：如果存在，检查是否有 admin 权限，没有就加上 ===
            if user.get("role") != "admin":
                print("检测到管理员账号权限缺失，正在修复...")
                self.db.users.update_one(
                    {"email": admin_email},
                    {"$set": {"role": "admin"}}
                )
    def set_current_user(self, user_id):
        self.current_user_id = user_id

    # ================= 1. 用户认证与资料模块 =================

    def register_user(self, email, username, password):
        if self.db.users.find_one({"email": email}):
            return False, "该邮箱已被注册"
        
        user_data = {
            "email": email,
            "username": username,
            "password_hash": generate_password_hash(password),
            "avatar": "default.png", 
            "bio": "这位同学很懒，什么也没写",
            "role": "user",  # 默认为普通用户
            "banned_until": None, # 封禁截止时间
            "created_at": datetime.datetime.now()
        }
        try:
            self.db.users.insert_one(user_data)
            return True, "注册成功"
        except Exception as e:
            return False, str(e)

    def get_user_by_email(self, email):
        return self.db.users.find_one({"email": email})

    def get_user_by_id(self, user_id):
        try:
            return self.db.users.find_one({"_id": ObjectId(user_id)})
        except:
            return None

    def update_profile(self, user_id, new_username, new_bio, new_avatar_filename=None):
        update_data = {
            "username": new_username,
            "bio": new_bio
        }
        if new_avatar_filename:
            update_data["avatar"] = new_avatar_filename
            
        self.db.users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": update_data}
        )
        return True

    def get_user_stats(self, user_id):
        """修复 Bio 不显示的问题：同时查询用户基本信息"""
        try:
            uid = ObjectId(user_id)
            # === 修复开始：查询用户信息获取 bio ===
            user_info = self.db.users.find_one({"_id": uid})
            bio = user_info.get("bio", "暂无简介") if user_info else ""
            # === 修复结束 ===

            q_count = self.db.question.count_documents({"author_id": uid})
            a_count = self.db.answer.count_documents({"author_id": uid})
            
            pipeline_q = [{"$match": {"author_id": uid}}, {"$project": {"count": {"$size": {"$ifNull": ["$vote_up_users", []]}}}}]
            q_votes = sum(doc['count'] for doc in self.db.question.aggregate(pipeline_q))
            
            pipeline_a = [{"$match": {"author_id": uid}}, {"$project": {"count": {"$size": {"$ifNull": ["$vote_up_users", []]}}}}]
            a_votes = sum(doc['count'] for doc in self.db.answer.aggregate(pipeline_a))
            
            return {
                "question_count": q_count,
                "answer_count": a_count,
                "vote_count": q_votes + a_votes,
                "bio": bio  # 返回 bio
            }
        except:
            return {"question_count": 0, "answer_count": 0, "vote_count": 0, "bio": ""}

    # ================= 2. 权限与管理模块 (新增) =================

    def check_is_banned(self, user_id):
        """检查用户是否被封禁"""
        user = self.get_user_by_id(user_id)
        if user and user.get('banned_until'):
            if user['banned_until'] > datetime.datetime.now():
                return True, user['banned_until']
        return False, None

    def ban_user(self, user_id, days):
        """封禁用户"""
        until = datetime.datetime.now() + datetime.timedelta(days=int(days))
        self.db.users.update_one({"_id": ObjectId(user_id)}, {"$set": {"banned_until": until}})
        return True

    def delete_content(self, doc_id, doc_type):
        """删除问题或回答"""
        try:
            oid = ObjectId(doc_id)
            if doc_type == 'question':
                self.db.question.delete_one({"_id": oid})
                # 级联删除该问题下的所有回答
                self.db.answer.delete_many({"question_id": oid})
            elif doc_type == 'answer':
                self.db.answer.delete_one({"_id": oid})
            return True
        except:
            return False
        
    def toggle_pin_question(self, question_id):
        """置顶/取消置顶问题"""
        try:
            oid = ObjectId(question_id)
            question = self.db.question.find_one({"_id": oid})
            new_status = not question.get('is_pinned', False)
            self.db.question.update_one({"_id": oid}, {"$set": {"is_pinned": new_status}})
            return True, new_status
        except:
            return False, False


    def toggle_pin_answer(self, answer_id):
        """置顶/取消置顶回答"""
        try:
            oid = ObjectId(answer_id)
            answer = self.db.answer.find_one({"_id": oid})
            new_status = not answer.get('is_pinned', False)
            self.db.answer.update_one({"_id": oid}, {"$set": {"is_pinned": new_status}})
            return True, new_status
        except:
            return False, False

    # ================= 3. 提问与回答模块（写入） =================

    def insert_question(self, title, detail, author_id):
        # 插入前先检查封禁
        is_banned, until = self.check_is_banned(author_id)
        if is_banned:
            return False, f"你已被禁言至 {until.strftime('%Y-%m-%d %H:%M')}"

        data = {
            "title": title,
            "detail": detail,
            "author_id": ObjectId(author_id),
            "ask_time": datetime.datetime.now(),
            "vote_up_users": [],
            "vote_down_users": []
        }
        self.db.question.insert_one(data)
        return True, "发布成功"

    def insert_answer(self, question_id, answer_content, author_id):
        # 插入前先检查封禁
        is_banned, until = self.check_is_banned(author_id)
        if is_banned:
            return False, f"你已被禁言至 {until.strftime('%Y-%m-%d %H:%M')}"

        data = {
            "question_id": ObjectId(question_id),
            "answer": answer_content,
            "author_id": ObjectId(author_id),
            "answer_time": datetime.datetime.now(),
            "vote_up_users": [],
            "vote_down_users": [],
            "is_pinned": False # 新增置顶字段
        }
        self.db.answer.insert_one(data)
        return True, "发布成功"

    # ================= 4. 查询模块 =================

    def query_question(self):
        pipeline = [
            {"$lookup": {"from": "users", "localField": "author_id", "foreignField": "_id", "as": "user_info"}},
            {"$unwind": "$user_info"},
            { "$sort": {"is_pinned": -1, "ask_time": -1} }
        ]
        
        cursor = self.db.question.aggregate(pipeline)
        question_list = []
        
        for q in cursor:
            up_list = q.get("vote_up_users", [])
            down_list = q.get("vote_down_users", [])
            
            my_vote_status = "none"
            if self.current_user_id:
                if self.current_user_id in up_list: my_vote_status = "up"
                elif self.current_user_id in down_list: my_vote_status = "down"

            ask_time_str = q.get("ask_time").strftime("%Y-%m-%d") if isinstance(q.get("ask_time"), datetime.datetime) else str(q.get("ask_time"))

            data = {
                "question_id": str(q["_id"]),
                "title": q.get("title"),
                "detail": q.get("detail"),
                "author": q["user_info"]["username"],
                "author_id": str(q["author_id"]), # 返回作者ID用于前端判断
                "author_avatar": q["user_info"].get("avatar", "default.png"),
                "author_role": q["user_info"].get("role", "user"),
                "is_pinned": q.get("is_pinned", False),

                "ask_time": ask_time_str,
                "vote_up": len(up_list) - len(down_list),
                "answer_number": self.db.answer.count_documents({"question_id": q["_id"]}),
                "my_vote": my_vote_status
            }
            question_list.append(data)
        return question_list

    def query_answer(self, question_id):
        oid = ObjectId(question_id)
        
        # 查问题
        pipeline_q = [
            {"$match": {"_id": oid}},
            {"$lookup": {"from": "users", "localField": "author_id", "foreignField": "_id", "as": "user_info"}},
            {"$unwind": "$user_info"}
        ]
        q_docs = list(self.db.question.aggregate(pipeline_q))
        if not q_docs: return {}
        q_doc = q_docs[0]

        # 查回答
        pipeline_a = [
            {"$match": {"question_id": oid}},
            {"$lookup": {"from": "users", "localField": "author_id", "foreignField": "_id", "as": "user_info"}},
            {"$unwind": "$user_info"}
        ]
        a_cursor = self.db.answer.aggregate(pipeline_a)
        
        answer_list_data = []
        for a in a_cursor:
            up_list = a.get("vote_up_users", [])
            down_list = a.get("vote_down_users", [])
            
            data = {
                "answer_id": str(a["_id"]),
                "answer_author": a["user_info"]["username"],
                "author_id": str(a["author_id"]), # 用于前端判断删除权限
                "author_avatar": a["user_info"].get("avatar", "default.png"),
                "author_role": a["user_info"].get("role", "user"),
                "answer_detail": a.get("answer"),
                "answer_vote": len(up_list) - len(down_list),
                "is_upvoted": self.current_user_id in up_list if self.current_user_id else False,
                "is_downvoted": self.current_user_id in down_list if self.current_user_id else False,
                "is_pinned": a.get("is_pinned", False) # 传递置顶状态
            }
            answer_list_data.append(data)
        
        # 排序：先置顶的，然后按票数高低
        answer_list_data.sort(key=lambda x: (not x['is_pinned'], -x['answer_vote']))

        return {
            "question_id": str(q_doc["_id"]),
            "question_title": q_doc.get("title"),
            "question_detail": q_doc.get("detail"),
            "question_author_id": str(q_doc["author_id"]), # 用于前端判断
            "answer_num": len(answer_list_data),
            "answer_list": answer_list_data
        }

    def update_vote(self, doc_id, doc_type, direction, user_id):
        # ... (保持原样，省略以节省空间，直接用你原来的 update_vote 代码) ...
        try:
            collection = self.db.question if doc_type == 'question' else self.db.answer
            oid = ObjectId(doc_id)
            doc = collection.find_one({"_id": oid})
            
            if not doc: return False, 0
            
            up_users = doc.get("vote_up_users", [])
            down_users = doc.get("vote_down_users", [])
            
            target_list = up_users if direction == 'vote_up' else down_users
            other_list = down_users if direction == 'vote_up' else up_users
            
            if user_id in target_list:
                target_list.remove(user_id)
            else:
                target_list.append(user_id)
                if user_id in other_list:
                    other_list.remove(user_id)
            
            update_data = {
                "vote_up_users": up_users if direction == 'vote_up' else other_list,
                "vote_down_users": down_users if direction == 'vote_down' else other_list
            }
            collection.update_one({"_id": oid}, {"$set": update_data})
            
            return True, len(update_data["vote_up_users"]) - len(update_data["vote_down_users"])

        except Exception as e:
            print(f"Vote Error: {e}")
            return False, 0
        
        # ================= 5. 公开个人主页查询 (新增) =================
    
    def get_public_profile(self, user_id):
        """获取某用户的公开资料、提问列表、回答列表"""
        try:
            uid = ObjectId(user_id)
            user = self.db.users.find_one({"_id": uid})
            if not user: return None

            # 1. 基础信息
            profile = {
                "user_id": str(user["_id"]),
                "username": user["username"],
                "avatar": user.get("avatar", "default.png"),
                "bio": user.get("bio", "暂无介绍"),
                "role": user.get("role", "user"),
                "join_date": user.get("created_at", datetime.datetime.now()).strftime("%Y-%m-%d")
            }

            # 2. 他的提问
            q_cursor = self.db.question.find({"author_id": uid}).sort("ask_time", -1)
            questions = []
            for q in q_cursor:
                questions.append({
                    "id": str(q["_id"]),
                    "title": q["title"],
                    "time": q["ask_time"].strftime("%Y-%m-%d"),
                    "vote_count": len(q.get("vote_up_users", [])) - len(q.get("vote_down_users", []))
                })

            # 3. 他的回答 (需要关联查出是哪个问题的回答)
            pipeline = [
                {"$match": {"author_id": uid}},
                {"$sort": {"answer_time": -1}},
                {
                    "$lookup": {
                        "from": "question",
                        "localField": "question_id",
                        "foreignField": "_id",
                        "as": "question_info"
                    }
                },
                {"$unwind": "$question_info"}
            ]
            a_cursor = self.db.answer.aggregate(pipeline)
            answers = []
            for a in a_cursor:
                answers.append({
                    "answer_id": str(a["_id"]),
                    "question_id": str(a["question_info"]["_id"]),
                    "question_title": a["question_info"]["title"],
                    "preview": a["answer"][:50] + "..." if len(a["answer"]) > 50 else a["answer"],
                    "time": a["answer_time"].strftime("%Y-%m-%d"),
                    "vote_count": len(a.get("vote_up_users", [])) - len(a.get("vote_down_users", []))
                })

            return {
                "profile": profile,
                "questions": questions,
                "answers": answers,
                "stats": {
                    "q_count": len(questions),
                    "a_count": len(answers)
                }
            }
        except Exception as e:
            print(f"Profile Error: {e}")
            return None