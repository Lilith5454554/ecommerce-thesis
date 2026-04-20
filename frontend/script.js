// 后端API网关地址
const API_BASE = 'http://localhost:8000';
let authToken = null;  // 存储JWT token

// 辅助函数：发送请求
async function request(endpoint, method, body = null, needAuth = false) {
    const headers = {
        'Content-Type': 'application/json',
    };
    if (needAuth && authToken) {
        headers['Authorization'] = `Bearer ${authToken}`;
    }
    const options = {
        method,
        headers,
    };
    if (body) {
        options.body = JSON.stringify(body);
    }
    const response = await fetch(`${API_BASE}${endpoint}`, options);
    if (!response.ok) {
        const error = await response.text();
        throw new Error(`请求失败: ${response.status} ${error}`);
    }
    return response.json();
}

// 注册
document.getElementById('registerBtn').onclick = async () => {
    const username = document.getElementById('regUsername').value;
    const email = document.getElementById('regEmail').value;
    const password = document.getElementById('regPassword').value;
    if (!username || !email || !password) {
        alert('请填写完整信息');
        return;
    }
    try {
        const data = await request('/users/', 'POST', { username, email, password });
        alert(`注册成功！用户ID: ${data.id}`);
    } catch (err) {
        alert(`注册失败: ${err.message}`);
    }
};

// 登录
document.getElementById('loginBtn').onclick = async () => {
    const username = document.getElementById('loginUsername').value;
    const password = document.getElementById('loginPassword').value;
    if (!username || !password) {
        alert('请填写用户名和密码');
        return;
    }
    try {
        const data = await request('/auth/login', 'POST', { username, password });
        authToken = data.access_token;
        document.getElementById('userInfo').innerHTML = `已登录: ${username} (Token 已保存)`;
        alert('登录成功！');
    } catch (err) {
        alert(`登录失败: ${err.message}`);
    }
};

// 刷新商品列表
document.getElementById('listProductsBtn').onclick = async () => {
    try {
        const products = await request('/products/', 'GET');
        const listEl = document.getElementById('productList');
        listEl.innerHTML = '';
        products.forEach(p => {
            const li = document.createElement('li');
            li.textContent = `${p.name} - 价格: ¥${p.price} - 库存: ${p.stock} (ID: ${p.id})`;
            listEl.appendChild(li);
        });
    } catch (err) {
        alert(`获取商品失败: ${err.message}`);
    }
};

// 创建商品（需要登录？根据你的后端，商品创建接口通常不需要认证，但为了安全可以不加）
document.getElementById('createProductBtn').onclick = async () => {
    const name = document.getElementById('prodName').value;
    const price = parseFloat(document.getElementById('prodPrice').value);
    const stock = parseInt(document.getElementById('prodStock').value);
    if (!name || isNaN(price) || isNaN(stock)) {
        alert('请填写完整的商品信息');
        return;
    }
    try {
        const data = await request('/products/', 'POST', { name, price, stock });
        alert(`商品创建成功！ID: ${data.id}`);
        // 刷新列表
        document.getElementById('listProductsBtn').click();
    } catch (err) {
        alert(`创建商品失败: ${err.message}`);
    }
};

// 创建订单（需要认证）
document.getElementById('createOrderBtn').onclick = async () => {
    if (!authToken) {
        alert('请先登录');
        return;
    }
    const productId = document.getElementById('orderProductId').value;
    const quantity = parseInt(document.getElementById('orderQuantity').value);
    const address = document.getElementById('shippingAddress').value;
    if (!productId || isNaN(quantity) || !address) {
        alert('请填写完整订单信息');
        return;
    }
    try {
        // 需要先获取商品详情以得到 product_name 和 price，简化：假设商品存在且价格已知
        // 更好的做法是先调用 /products/{id} 获取商品信息
        const product = await request(`/products/${productId}`, 'GET');
        const orderData = {
            user_id: 'demo-user-id',   // 实际应从 token 中解析，但为简化，我们传递一个模拟值
            items: [{
                product_id: productId,
                product_name: product.name,
                quantity: quantity,
                price: product.price
            }],
            shipping_address: address
        };
        const result = await request('/orders/', 'POST', orderData, true);
        document.getElementById('orderResult').innerHTML = `订单创建成功！订单ID: ${result.id}, 总金额: ¥${result.total_amount}`;
    } catch (err) {
        alert(`创建订单失败: ${err.message}`);
    }
};