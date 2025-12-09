from your_code_here.MongoUtil import MongoUtil

# 连接数据库
mongo = MongoUtil()

admin_email = "admin@quest.bupang.xyz"

# 查找该用户
user = mongo.db.users.find_one({"email": admin_email})

if user:
    print(f"找到用户: {user['username']}")
    # 强制更新角色为 admin
    mongo.db.users.update_one(
        {"email": admin_email},
        {"$set": {"role": "admin"}}
    )
    print("✅ 成功！该用户已升级为管理员。")
else:
    print("❌ 未找到该邮箱用户，请检查 MongoUtil 的 _init_admin 是否运行，或者手动注册一个同名账号。")



