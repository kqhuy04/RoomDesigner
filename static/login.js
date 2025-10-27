document.getElementById("login-form").addEventListener("submit", async function(event) {
    event.preventDefault();
    const username = document.getElementById("username").value;
    const password = document.getElementById("password").value;
    const errorMessage = document.getElementById("login-error-message");
    errorMessage.style.display = "none";
    errorMessage.textContent = "";

    try {
        const response = await fetch("/login", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ username, password })
        });
        const data = await response.json();
        if (response.ok) {
            alert("Login successful!");
        } else {
            errorMessage.textContent = data.message || 'Đăng nhập thất bại!';
            errorMessage.style.display = 'block';
        }
    } catch (error) {
        errorMessage.textContent = 'Có lỗi xảy ra, vui lòng thử lại!';
        errorMessage.style.display = 'block';
    }
    
});