import pymongo

# 连接数据库
client = pymongo.MongoClient("mongodb://lixongchuan:lichuan430@117.72.52.104:27017/")

# 直接删除整个 qa_system 数据库
client.drop_database("qa_system")

print("数据库已成功清空！请重新运行 main.py 并注册新用户。")
