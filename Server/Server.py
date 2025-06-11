from flask import Flask, request, jsonify, send_file
import os

app = Flask(__name__)
BASE_DIR = os.path.join(os.getcwd(), "received")
os.makedirs(BASE_DIR, exist_ok=True)

@app.route("/authenticate", methods=["POST"])
def authenticate():
    """Authenticate the user and create a directory for them."""
    data = request.json
    username = data.get("username")
    password = data.get("password")  # Dummy authentication for simplicity
    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400
    home_directory = os.path.join(BASE_DIR, username)
    os.makedirs(home_directory, exist_ok=True)
    return jsonify({"message": "Authentication successful", "home_directory": home_directory}), 200

@app.route("/list", methods=["POST"])
def list_files():
    """List files in the user's directory."""
    data = request.json
    home_directory = data.get("home_directory")
    if not home_directory or not os.path.exists(home_directory):
        return jsonify({"error": f"Directory not found: {home_directory}"}), 404
    files = os.listdir(home_directory)
    return jsonify({"files": files}), 200

@app.route("/upload", methods=["POST"])
def upload_file():
    """Upload a file to the user's directory."""
    home_directory = request.form.get("home_directory")
    file = request.files.get("file")
    if not home_directory or not file:
        return jsonify({"error": "Incomplete data"}), 400
    file_path = os.path.join(home_directory, file.filename)
    file.save(file_path)
    return jsonify({"message": f"File uploaded to {file_path}"}), 200

@app.route("/download", methods=["POST"])
def download_file():
    """Download a file from the user's directory."""
    data = request.json
    filename = data.get("filename")
    home_directory = data.get("home_directory")
    if not filename or not home_directory:
        return jsonify({"error": "Filename and home_directory are required"}), 400
    file_path = os.path.join(home_directory, filename)
    if not os.path.exists(file_path):
        return jsonify({"error": f"File not found: {file_path}"}), 404
    return send_file(file_path, as_attachment=True)

@app.route("/delete", methods=["POST"])
def delete_file():
    """Delete a file from the user's directory."""
    data = request.json
    filename = data.get("filename")
    home_directory = data.get("home_directory")
    if not filename or not home_directory:
        return jsonify({"error": "Filename and home_directory are required"}), 400
    file_path = os.path.join(home_directory, filename)
    if not os.path.exists(file_path):
        return jsonify({"error": f"File not found: {file_path}"}), 404
    os.remove(file_path)
    return jsonify({"message": f"File '{filename}' deleted successfully"}), 200

if __name__ == "__main__":
    app.run(debug=True, threaded=True)
