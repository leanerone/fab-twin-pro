"""测试模型文件上传接口"""
import requests
import os

BASE_URL = "http://localhost:8002"

def test_upload():
    """测试上传 SVG 文件"""
    svg_content = b'''<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200">
        <rect width="100" height="100" fill="red"/>
        <circle cx="150" cy="100" r="50" fill="blue"/>
    </svg>'''
    
    files = {'file': ('test-model.svg', svg_content, 'image/svg+xml')}
    data = {
        'model_id': 'PODOPENER-2200',
        'uploaded_by': 'admin',
        'description': '测试上传'
    }
    
    print("1. 测试上传文件...")
    resp = requests.post(f"{BASE_URL}/api/uploads/models", files=files, data=data)
    print(f"   状态码: {resp.status_code}")
    if resp.status_code == 200:
        result = resp.json()
        print(f"   文件ID: {result.get('file_id')}")
        print(f"   版本: {result.get('version')}")
        print(f"   文件名: {result.get('file_name')}")
        print(f"   文件路径: {result.get('file_path')}")
        print("   ✅ 上传成功!")
        
        # 保存 file_id 用于后续测试
        return result.get('file_id')
    else:
        print(f"   错误: {resp.text}")
        return None

def test_list(model_id='PODOPENER-2200'):
    """测试查询文件列表"""
    print("\n2. 测试查询文件列表...")
    resp = requests.get(f"{BASE_URL}/api/uploads/models", params={'model_id': model_id})
    print(f"   状态码: {resp.status_code}")
    if resp.status_code == 200:
        result = resp.json()
        print(f"   文件数量: {result.get('total')}")
        for f in result.get('files', []):
            print(f"   - {f['file_name']} ({f['version']}, {f['file_size']} bytes)")
        print("   ✅ 查询成功!")
    else:
        print(f"   错误: {resp.text}")

def test_delete(file_id, model_id='PODOPENER-2200'):
    """测试删除文件"""
    print(f"\n3. 测试删除文件 {file_id}...")
    resp = requests.delete(f"{BASE_URL}/api/uploads/models/{file_id}", params={'model_id': model_id})
    print(f"   状态码: {resp.status_code}")
    if resp.status_code == 200:
        print(f"   响应: {resp.json()}")
        print("   ✅ 删除成功!")
    else:
        print(f"   错误: {resp.text}")

if __name__ == '__main__':
    print("=" * 50)
    print("FabTwin 模型上传接口测试")
    print("=" * 50)
    
    # 检查服务是否可用
    try:
        resp = requests.get(f"{BASE_URL}/health")
        print(f"\n✅ 后端服务运行正常: {resp.json()}")
    except Exception as e:
        print(f"\n❌ 后端服务不可用: {e}")
        exit(1)
    
    # 执行测试
    file_id = test_upload()
    if file_id:
        test_list()
        # test_delete(file_id)  # 暂时不删除，保留测试数据
    
    print("\n" + "=" * 50)
    print("测试完成!")
    print("=" * 50)
