import rospy
from sensor_msgs.msg import Image
from std_msgs.msg import String, Bool
from cv_bridge import CvBridge
import cv2
from ultralytics import YOLO
import supervision as sv
import os
import json
import time


# Soglia dell'area per considerare una faccia come "pronta per interagire"
AREA_THRESHOLD = 2500

class FaceRecognition:
    # Costruttore della classe FaceRecognition
    # model_size: dimensione del modello YOLO (s, m, l, x)
    # verbose: stampa i dettagli del modello YOLO
    # device: dispositivo su cui eseguire il modello YOLO (cpu, cuda)
    # conf_threshold: soglia di confidenza per il riconoscimento facciale
    # min_area_threshold: soglia minima dell'area del bounding box
    def __init__(self, model_size="n", tracking=True, verbose=False, device="cpu", conf_threshold=0.6, min_area_threshold=0.003): #was 0.005
        # Dimensioni dell'immagine
        self.IMG_WIDTH = 672
        self.IMG_HEIGHT = 376
        self.image_area = self.IMG_WIDTH * self.IMG_HEIGHT
        self.model_size = model_size
        self.tracker = sv.ByteTrack() if tracking else None 
        self.confidence_threshold = conf_threshold
        self.th_area = min_area_threshold
        self.verbose = verbose
        self.device = device
        self.bridge = CvBridge()  # Per convertire tra immagini ROS e OpenCV
        self.load_yolo()  # Carica il modello YOLO
        self.load_annotators()  # Carica gli annotatori
        self.init_ros()  # Inizializza ROS

    def load_yolo(self):
        """Carica il modello YOLO per il riconoscimento facciale."""
        current_directory = os.path.dirname(os.path.abspath(__file__))
        target_directory = os.path.join(current_directory, "../models")
        os.chdir(target_directory)
        # Carica il modello YOLO specificato
        self.model = YOLO('https://github.com/akanametov/yolov8-face/releases/download/v0.0.0/yolov8' + self.model_size + '-face.pt')

    def load_annotators(self):
        self.box_annotator = sv.BoxAnnotator()  # Annotatore per i bounding box
        if self.tracker is not None:
            self.label_annotator = sv.LabelAnnotator()

    def recognize_faces(self, frame):
        """Riconosce le facce in un frame e restituisce il risultato e l'immagine annotata."""
        result = self.model(frame, verbose=self.verbose, device=self.device)[0]
        detected_faces = sv.Detections.from_ultralytics(result)

        # Filtra le facce per soglia di confidenza
        detected_faces = detected_faces[detected_faces.confidence > self.confidence_threshold]
        # Filtra le facce per area
        detected_faces = detected_faces[(detected_faces.area/self.image_area > self.th_area)]

        # Se tracker enabled assegna ID ai volti
        if self.tracker is not None:
            detected_faces = self.tracker.update_with_detections(detected_faces)
            labels = [f"#{tracker_id}" for tracker_id in detected_faces.tracker_id]
            frame = self.label_annotator.annotate(scene=frame, detections=detected_faces, labels=labels)
            # print("Detected faces IDs: ", detected_faces.tracker_id) 

        # Annotazione dell'immagine con i bounding box
        annotated_image = self.box_annotator.annotate(scene=frame, detections=detected_faces)
        return detected_faces, annotated_image

    def init_ros(self):
        """Inizializza ROS e imposta i publisher."""
        rospy.init_node('face_recognition', anonymous=False)
        robot_name = os.getenv('ROBOT_NAME', 'robot_alterego3')
        self.pub_image = rospy.Publisher(f'/{robot_name}/annotated_faces', Image, queue_size=10)
        self.pub_ready2interact = rospy.Publisher(f'/{robot_name}/ready2interact', Bool, queue_size=10)
        self.pub_annotation = rospy.Publisher(f'/{robot_name}/detections', String, queue_size=10)
        self.rate = rospy.Rate(60)  # Frequenza di pubblicazione a 15 Hz

    def process_camera(self, camera):
        # cv2.namedWindow("annotated_image", cv2.WINDOW_NORMAL)
        # cv2.resizeWindow("annotated_image", self.IMG_WIDTH, self.IMG_HEIGHT)
        
        """Elabora i frame dalla telecamera e pubblica i risultati."""
        while not rospy.is_shutdown():
            ret, frame = camera.read()
            # Divide l'immagine a metà orizzontalmente (un occhio del robot)
            frame = frame[:, 0:int(frame.shape[1])]
            if not ret:
                rospy.logerr("Can't read frame from camera")
                break
            detected_faces, annotated_image = self.recognize_faces(frame)

            dictionary = {}
            if len(detected_faces.xyxy) > 0:
                # Calcola l'area dei bounding box
                areas = []
                for i, detection in enumerate(detected_faces.xyxy):
                    # Componi il messaggio da pubblicare
                    dictionary["face " + str(i)] = detection.tolist()

                    # Calcola l'area del bounding box
                    area = (detection[2] - detection[0]) * (detection[3] - detection[1])
                    areas.append(area)
                    # print("Face", i+1 , ": Area = ", area)
                    if area > AREA_THRESHOLD:
                        self.pub_ready2interact.publish(True)
                        # print("Face", i+1 , ": \033[92m", "READY" "\033[0m")
                    else:
                        self.pub_ready2interact.publish(False)
                        # print("Face", i+1 ,": \033[91m", "NOT READY" "\033[0m")
            else:
                self.pub_ready2interact.publish(False)
                # print("No face detected")
            
            # Pubblica le annotazioni come stringa JSON
            self.pub_annotation.publish(json.dumps(dictionary))
            
            # print("-------------------------------------------------")
            try:
                # Show the annotated image
                # cv2.imshow("annotated_image", annotated_image)
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    rospy.loginfo("User requested shutdown")
                    break
            except Exception as e:
                rospy.logerr(f"Error displaying frame: {e}")
            # self.pub_image.publish(self.bridge.cv2_to_imgmsg(annotated_image, "bgr8"))
            self.rate.sleep()



def try_open_camera(max_attempts=5, delay=2):
    """Tenta di aprire la telecamera con un numero massimo di tentativi."""
    for attempt in range(max_attempts):
        camera = cv2.VideoCapture(4)
        if camera.isOpened():
            rospy.loginfo(f"Camera opened successfully on attempt {attempt + 1}")
            return camera
        else:
            rospy.logwarn(f"Attempt {attempt + 1} failed to open camera. Retrying in {delay} seconds...")
            camera.release()
            time.sleep(delay)
    rospy.logerr("Failed to open camera after multiple attempts.")
    return None

if __name__ == "__main__":
    camera = try_open_camera()  # Tenta di aprire la telecamera
    if camera is not None:
        face_recognition = FaceRecognition()  # Crea un'istanza della classe FaceRecognition
        face_recognition.process_camera(camera)  # Elabora i frame dalla telecamera
        camera.release()  # Rilascia la telecamera
        cv2.destroyAllWindows()  # Chiude tutte le finestre di OpenCV
    else:
        rospy.logerr("Exiting due to camera initialization failure.")