import json
import cv2 as cv
import numpy as np
import fitz, math

QUALITY = 1
THRESHOLD = 150

def count_pdf(filename):
    pdf = fitz.open(filename)
    pages = pdf.page_count
    pdf.close()

    return pages

class Processor:
    def __init__(self, images):
        self.images = images

    def pil_to_cv(self, image):
        cv_image = np.array(image) 
        cv_image = cv_image[:, :, ::-1].copy() 

        return cv_image

    def get_blank_transparent(self, shape):
        b_channel = np.ones((shape[0], shape[1]), dtype=np.uint8) * 255
        r_channel = np.ones((shape[0], shape[1]), dtype=np.uint8) * 255
        g_channel = np.ones((shape[0], shape[1]), dtype=np.uint8) * 255
        alpha_channel = np.ones((shape[0], shape[1]), dtype=np.uint8) * 0

        image = cv.merge((b_channel, g_channel, r_channel, alpha_channel))

        return image

    def get_image(self, index):
        image = self.pil_to_cv(self.images[index])
        # image = self.images[index]

        (height, width, _) = image.shape
        
        # Resize image
        image = cv.resize(image, (int(width * QUALITY), int(height * QUALITY)), interpolation=cv.INTER_AREA)

        # Convert to grayscale
        img_gray = cv.cvtColor(image, cv.COLOR_BGR2GRAY)

        # Get all colored pixels as black pixels
        _, thresh = cv.threshold(img_gray, THRESHOLD, 255, cv.THRESH_BINARY)

        # Invert to get all non-colored pixels as black pixels
        invert_thresh = cv.bitwise_not(thresh)

        # Add alpha channel to original image
        image = cv.cvtColor(image, cv.COLOR_BGR2BGRA)

        # Get blank white image, all pixels are (255, 255, 255, 0)
        blank = self.get_blank_transparent(image.shape)

        # To the alpha channel of the blank image, we can assign the scalar values of the inverted threshold image
        # The alpha channel has a 2d shape, so does the inverted threshold image, and we can treat the black pixels-
        # in the inverted threshold image as transparent pixels, if we assign all of these to the blank image,
        # the blank image will contain transparent white pixels where the black pixels would've been in the inverted
        # threshold image, and opaque white pixels where the white pixels would've been in the inverted threshold image
        blank[:, :, 3] = invert_thresh

        # Now, since all non-white pixels are now opaque, and white pixels are now transaprent, this is what would occur
        # during a bitwise AND operation:
        # If a pixel is non-white in the original image, it will remain opaque
        # If a pixel is white in the original image, it will become transparent
        return cv.bitwise_and(image, blank)

class Session:
    @staticmethod
    def get():
        with open("./sessions.json", "r") as file:
            return json.loads(file.read())

    @staticmethod
    def set(data):
        with open('./sessions.json', "w") as file:
            file.write(json.dumps(data))

    @staticmethod
    def delete(index):
        sessions = Session.get()
        del sessions[index]
        Session.set(sessions)
    
    def __init__(self, file=None, _id=None):
        if _id != None:
            self.id = _id
            return

        sessions = Session.get()

        self.id = self.acquire_id(sessions)

        pages = count_pdf(file)

        sessions.append({
            "id": self.id,
            "file": file,
            "data": [[]] * pages
        })

        Session.set(sessions)

        print(f'Initialized session "{self.id}" on file "{file}" with {pages} page(s)')


    def acquire_id(self, sessions):
        _id = 0
        if len(sessions) != 0:
            numbers = list(map(lambda e: e["id"], sessions))
            _id = list(sorted(numbers, reverse=True))[0] + 1
        return _id
            
    def change_data(self, page, data):
        sessions = Session.get()

        # print(sessions)
        index = next((i for i, e in enumerate(sessions) if e["id"] == self.id), -1)

        if index == -1:
            print(f'Failed to update sessions of ID "{self.id}"')
            return
        
        sessions[index]["data"][page] = data

        Session.set(sessions)

class Tool:
    def __init__(self, canvas, update):
        self.canvas = canvas
        self.update = update

class Highlighter(Tool):
    def __init__(self, canvas, update):
        super().__init__(canvas, update)

        self.rectangle = None
        self.origin = [0, 0]
        self.name = "highlight"
        
    def on_press(self, x, y, right=False):
        if right: return

        self.rectangle = self.canvas.create_rectangle(0, 0, 0, 0, fill="", outline="red")
        self.canvas.coords(self.rectangle, x, y, x, y)
        self.origin = [x, y]

    def on_move(self, xm, ym, data, right=False):
        if right: return

        x, y = self.origin
        self.canvas.coords(self.rectangle, min(xm, x), min(ym, y), max(xm, x), max(ym, y))

    def on_release(self, xm, ym, data, right=False):
        if not right:
            x, y = self.origin
            self.canvas.coords(self.rectangle, min(xm, x), min(ym, y), max(xm, x), max(ym, y))
            data.append({ "type": self.name, "info": self.get_info() })    
        else:
            # TODO: Make the eraser tool perform this, make a conditions dictionary as to indicate when an erase event would occur
            # Find the first item that is a highlight rectangle which also encompasses the current release mouse position
            # The enumerated list is reversed to maintain layer order
            result = next((item for item in reversed(list(enumerate(data))) if item[1]["type"] == self.name and self.inside_rect((xm, ym), item[1]["info"])), None)
            index = result[0] if result != None else -1

            if index == -1: return
        
            del data[index]

    def get_info(self):
        return self.canvas.coords(self.rectangle)

    def inside_rect(self, point, rect):
        x0, y0, x1, y1 = rect
        x, y = point
        return x >= x0 and x <= x1 and y >= y0 and y <= y1

    @staticmethod
    def render(canvas, info):
        x0, y0, x1, y1 = info
        canvas.create_rectangle(x0, y0, x1, y1, fill="yellow", outline="red")

    @staticmethod
    def export_render(engine, page, image, info):
        (height, width, _) = image.shape

        scale = 1 / min(721 / width, 1020 / height)

        x0, y0, x1, y1 = info
        x0 *= scale
        y0 *= scale
        x1 *= scale
        y1 *= scale

        rect = engine.Rect(x0, y0, x1, y1)

        shape = page.new_shape()
        shape.draw_rect(rect)
        shape.finish(width = 0.3, color = (1, 0, 0), fill = (1, 1, 0))
        shape.commit()

class Pencil(Tool):
    def __init__(self, canvas, update):
        super().__init__(canvas, update)

        self.rectangle = None
        self.drawing = None
        self.removing = []
        self.name = "pencil"
        
    def on_press(self, x, y, right=False):
        if right: return

        self.drawing = [
            [x, y, x, y, 1]
        ]

        self.canvas.create_line(x, y, x, y, fill="black", width=1)

    def on_move(self, xm, ym, data, right=False):
        if right:
            splines = list(filter(lambda e: e[1]["type"] == "pencil", list(enumerate(data))))
            offset = 10

            indices = []
            
            for spline in splines:
                for line in spline[1]["info"]:
                    x0, y0, x1, y1, _ = line
                    magnitude = math.sqrt((y1 - y0)**2 + (x1 - x0)**2)

                    maximum = 2 * math.sqrt(offset**2 + (magnitude / 2)**2)
                    mouse_dist = math.sqrt((ym - y0)**2 + (xm - x0)**2) + math.sqrt((ym - y1)**2 + (xm - x1)**2)

                    if mouse_dist <= maximum:
                        indices.append(spline[0])
                        break

            old = self.removing.copy()
            self.removing = self.removing + list(set(indices).difference(self.removing))

            if len(old) != len(self.removing):
                data[:] = list(map(lambda e: e[1] if e[0] not in self.removing else self.blur_spline(e[1]), list(enumerate(data))))
                self.update()

            return

        x0, y0, x1, y1, _ = self.drawing[-1]

        self.drawing.append([x1, y1, xm, ym, 1])
        self.canvas.create_line(x1, y1, xm, ym, fill="black", width=1)

    def on_release(self, xm, ym, data, right=False):
        if right:
            data[:] = list(map(lambda e: e[1], filter(lambda e: e[0] not in self.removing, list(enumerate(data)))))
            self.removing = []

            return

        x0, y0, x1, y1, _ = self.drawing[-1]

        self.drawing.append([x1, y1, xm, ym, 1])

        self.canvas.create_line(x1, y1, xm, ym, fill="black", width=1)

        self.drawing = self.simplify(self.drawing)
        # self.simplify(self.drawing)
        data.append({ "type": self.name, "info": self.get_info() })   

    def simplify(self, lines):
        points = list(map(lambda e: [e[0], e[1]], lines))
        print(points)

        threshold = 1.5
        previous_slope = None

        indices = []

        for i in range(0, len(points) - 1):
            slope = self.get_slope(points[i], points[i + 1])

            if previous_slope == None:
                previous_slope = slope
                continue            
            
            if previous_slope == 'vertical' or slope == 'vertical':
                if previous_slope == slope:
                    indices.append(i)
            else:
                if abs(slope - previous_slope) <= threshold:
                    indices.append(i)

            previous_slope = slope

        points = list(map(lambda e: e[1], filter(lambda e: e[0] not in indices, list(enumerate(points)))))

        for i in range(0, len(points) - 1):
            p1 = points[i]
            p2 = points[i + 1]

            points[i] = [p1[0], p1[1], p2[0], p2[1], 1]

        points[-1] = [points[-1][0], points[-1][1], points[-1][0], points[-1][1], 1]

        return points

    def get_slope(self, point1, point2):
        x0, y0 = point1
        x1, y1 = point2

        if x0 - x1 == 0: return 'vertical'
        
        return y1-y0/x1-x0

    def get_info(self):
        return self.drawing

    def blur_spline(self, spline):
        for i in range(len(spline["info"])):
            spline["info"][i][-1] = 0

        return spline

    @staticmethod
    def render(canvas, info):
        for x0, y0, x1, y1, alpha in info:
            canvas.create_line(x0, y0, x1, y1, fill="black" if alpha == 1 else "red", width=1)

    @staticmethod
    def export_render(engine, page, image, info):
        (height, width, _) = image.shape

        scale = 1 / min(721 / width, 1020 / height)

        points = list(map(lambda e: [e[0] * scale, e[1] * scale], info))
        shape = page.new_shape()
        shape.draw_polyline(points)
        shape.finish(width = 0.3, color = (0, 0, 0), fill = (1, 1, 1), fill_opacity=0)
        shape.commit()


class Text(Tool):
    def __init__(self, canvas, update):
        super().__init__(canvas, update)

        self.name = "text"
        
    def on_press(self, x, y, right=False):
        pass

    def on_move(self, xm, ym, data, right=False):
        pass

    def on_release(self, xm, ym, data, right=False):
        pass

    def get_info(self):
        return None

    @staticmethod
    def render(canvas, info):
        pass

    @staticmethod
    def export_render(engine, page, image, info):
        pass