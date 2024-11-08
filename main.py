from flask import Flask, render_template, Response, url_for, request, redirect, jsonify, session
from flask_socketio import SocketIO, emit
import YogaPose
import mediapipe as mp
import cv2
import os
import heatmap
import pyttsx3
import json

app = Flask(__name__)
app.secret_key = 'mykey'
socket = SocketIO(app)

global camera
global yogaPose
global genHeatMap 



def landVal(i, j):
    # Define a dictionary to map positions to values
    position_mapping = {
        (0, 1): 13,  # left elbow
        (0, 2): 14,  # right elbow
        (1, 1): 26,  # right knee
        (1, 2): 27,  # left knee
        (2, 1): 12,  # right shoulder
        (2, 2): 11,  # left shoulder
        (3, 1): 23,  # left hip
        (3, 2): 24  # right hip
    }

    # Check if the position is in the dictionary, otherwise return IndexError
    try:
        return position_mapping[(i, j)]
    except KeyError:
        return IndexError


def clear_terminal():
    os.system('cls')


def checkPoseCompletion(bool_list):
    is_proper_pose = all(result[0] for result in bool_list)
    return is_proper_pose

def load_user_data():
    with open('static/json/userData.json', 'r') as file:
        return json.load(file)

def save_user_data(data):
    with open('static/json/userData.json', 'w') as file:
        json.dump(data, file, indent=4)


def update_pose(username):
    global yogaPose
    user_data = load_user_data()
    pose_name =  yogaPose
    # Find the user
    for user in user_data:
        if user['username'] == username:
                user['History'].append({"name": pose_name, "status": "complete"})
                print(f"added pos to {user['username']}") # debugging
                break

    save_user_data(user_data)

class CamInput:
    def __init__(self) -> None:
      
        self.mp_drawing = mp.solutions.drawing_utils
        self.mp_pose = mp.solutions.pose
        self.camera = cv2.VideoCapture(0)
        self.obj = YogaPose.MatchYogaPos()

        self.height = 640
        self.width = 640
        self.text = 'good'
        self.fontFace = cv2.FONT_HERSHEY_SIMPLEX
        self.fontScale = 0.5
        self.color = (0, 225, 0)  # Color in BGR format
        self.thickness = 1
        self.lineType = cv2.LINE_AA
        self.x1 = 10
        self.y1 = 10
        self.org = (self.x1, self.y1)
        self.isStarted = False
        self.isPoseCorrect = False
        self.done = False

    def genHeatMap(self,tempList):
        obj = heatmap.heatMap()
        obj.createHeatmap(tempList)

    def speak(self,tempList):
        engine = pyttsx3.init()
        engine.setProperty('rate', 150)  # Speed of speech
        parts = []

        body_parts = {
            0: "elbow",
            1: "knee",
            2: "shoulder",
            3: "hip",
        }

        for i in range(4):
            if not tempList[i][0]:
                parts.append(body_parts[i])
        
        if len(body_parts) > 1:
            part = ', '.join(parts[:-1]) + ', and ' + parts[-1]
        else:
            part = parts[0]
        
        to_say = f'Correct your {part}'
        engine.say(to_say)
        engine.runAndWait()

    def gen_frames(self, socket):
        self.frame_count = 0
        global genHeatMap
        genHeatMap = False
        # tts_thread = threading.Thread(target=self.speak)
        # tts_thread.start()
        with self.mp_pose.Pose(min_detection_confidence=0.5, min_tracking_confidence=0.5) as pose:
            while self.camera.isOpened():
                success, frame = self.camera.read()

                if not success:
                    break
                else:
                    image = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                    image.flags.writeable = False

                    res = pose.process(image)
                    image.flags.writeable = True
                    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

                self.mp_drawing.draw_landmarks(
                    image,
                    res.pose_landmarks,
                    self.mp_pose.POSE_CONNECTIONS,
                )

                if res.pose_landmarks:
                    temp_list = self.obj.matchYogaPos(res.pose_landmarks.landmark, yogaPose)

                    if not self.isPoseCorrect:
                        if checkPoseCompletion(temp_list):
                            self.isPoseCorrect = True
                            print(self.isPoseCorrect)
                            socket.emit('complete')

                    for i in range(4):
                        if not temp_list[i][0]:
                            for j in range(1, 3):
                                text1 = str(round(temp_list[i][j]))
                                x1 = int(res.pose_landmarks.landmark[landVal(i, j)].x * self.width) + 3
                                y1 = int(res.pose_landmarks.landmark[landVal(i, j)].y * self.height) + 3
                                org1 = (x1, y1)
                                color = (0, 0, 225)
                                cv2.putText(image, text1, org1, self.fontFace, self.fontScale, color, self.thickness,
                                            self.lineType)
                        elif temp_list[i][0]:
                            for j in range(1, 3):
                                color = (0, 225, 0)
                                x1 = int(res.pose_landmarks.landmark[landVal(i, j)].x * self.width) + 3
                                y1 = int(res.pose_landmarks.landmark[landVal(i, j)].y * self.height) + 3
                                org1 = (x1, y1)
                                cv2.putText(image, self.text, org1, self.fontFace, self.fontScale, color,
                                            self.thickness,
                                            self.lineType)

                if genHeatMap == True and self.done == False:
                    self.genHeatMap(temp_list)
                    self.done = True


                ret, buffer = cv2.imencode('.jpg', image)
                frame = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

    def close_cam(self):
        self.camera.release()


global cam_obj


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Load user data and check if the user exists
        user_data = load_user_data()
        for user in user_data:
            if user['username'] == username and user['password'] == password:
                session['username'] = username  # Store the user in session
                return redirect(url_for('home'))
        
        # Display error if credentials are invalid
        error = 'Invalid username or password. Please try again.'
        return render_template('login.html', error=error)
    
    return render_template('login.html')

@app.route('/')
def home():
    if 'username' in session:
        json_url = url_for('static', filename='json/pose_details.json')
        return render_template('index.html', json_url=json_url)
    else:
        return redirect(url_for('login'))

@app.route('/logout')
def logout():
    session.pop('username', None)  # Remove user from session
    return redirect(url_for('login'))

@app.route('/perform', methods=['POST'])
def perform():
    global yogaPose
    yogaPose = request.form.get('selected_pose')
    print(yogaPose)
    return redirect(url_for('yoga'))


@app.route('/yoga')
def yoga():
    global cam_obj
    cam_obj = CamInput()

    return render_template('yoga.html', pose=yogaPose, poseComplete=cam_obj.isPoseCorrect)


@app.route('/video_feed')
def video_feed():
    return Response(cam_obj.gen_frames(socket), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/close_webcam', methods=['POST'])
def close_webcam():
    global camera
    global cam_obj
    # Release the camera resources
    cam_obj.close_cam()
    return "Webcam Closed"


@socket.on('connect')
def connect():
    print('Socket Connected')

@socket.on('heatmap')
def conn():
    print('here') #debugging
    global genHeatMap
    genHeatMap = True 

@socket.on('storeAngle')
def storeAngles():
    user = session.get('username')  # Ensure session is properly accessed
    if user:
        update_pose(user)

@app.route('/user_data')
def user_data():
    with open('static/json/userData.json', 'r') as f:
        users = json.load(f)
    current_user = session.get('username')

    user_data = next((user for user in users if user['username'] == current_user), None)

    return render_template('user_data.html', user=user_data)

@app.route('/meditation')
def meditation():
    return render_template('meditation.html')

if __name__ == "__main__":
    socket.run(app, allow_unsafe_werkzeug=True, debug=True)
