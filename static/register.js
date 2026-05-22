document.getElementById("register-form").addEventListener("submit", async function(event) {
    event.preventDefault();
    const username = document.getElementById("reg-username").value;
    const password = document.getElementById("reg-password").value;
    const errorMessage = document.getElementById("register-error-message");
    errorMessage.style.display = "none";
    errorMessage.textContent = "";

    try {
        const response = await fetch("/register", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ username, password })
        });
        const data = await response.json();
        if (response.ok) {
            alert("Register successful!");
        } else {
            errorMessage.textContent = data.message || 'Đăng ký thất bại!';
            errorMessage.style.display = 'block';
        }
    } catch (error) {
        errorMessage.textContent = 'Có lỗi xảy ra, vui lòng thử lại!';
        errorMessage.style.display = 'block';
    }
    
});