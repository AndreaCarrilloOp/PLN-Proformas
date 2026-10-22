const form = document.getElementById("loginForm");
const username = document.getElementById("username");
const password = document.getElementById("password");
const errorBox = document.getElementById("loginError");
const loginBtn = document.getElementById("loginBtn");
const togglePassword = document.getElementById("togglePassword");

togglePassword.addEventListener("click", () => {
  const reveal = password.type === "password";
  password.type = reveal ? "text" : "password";
  togglePassword.textContent = reveal ? "Ocultar" : "Mostrar";
  togglePassword.setAttribute("aria-label", reveal ? "Ocultar contraseña" : "Mostrar contraseña");
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorBox.textContent = "";
  loginBtn.disabled = true;
  loginBtn.textContent = "Ingresando…";

  try {
    const response = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: username.value.trim(),
        password: password.value,
      }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.detail || "No fue posible iniciar sesión");
    }
    window.location.replace("/");
  } catch (error) {
    errorBox.textContent = error.message || "Usuario o contraseña incorrectos";
    password.select();
  } finally {
    loginBtn.disabled = false;
    loginBtn.textContent = "Entrar";
  }
});
