__author__ = 'tiantheunissen@gmail.com'
__description__ = 'FlickerTag - A handy dandy little app for manually annotating image change detection patches.'

import sys
from functools import partial
import os
import cv2
from matplotlib import colors
from osgeo import gdal
import pickle
import numpy as np

from PyQt5.QtWidgets import QApplication, QLabel, QWidget, QPushButton, \
    QFileDialog, QSizePolicy, QGridLayout, QComboBox, QInputDialog, QPlainTextEdit, QFrame
from PyQt5.QtGui import QPixmap, QPainter, QBrush, QColor, QPen
from PyQt5.QtCore import Qt, QPoint

# Current directory
dir_path = os.path.dirname(os.path.realpath(__file__))

# ---------------------------------------------
# Automatic mode parameters
# ---------------------------------------------

# Where to find the reference images
global_a_dir = os.path.join(dir_path, 'A')
# Where to find the target images
global_b_dir = os.path.join(dir_path, 'B')
# Where to save the results
global_out_dir = os.path.join(dir_path, 'OUT')

# What tag to use for identifying reference images
a_tag = '_2018_'
# What tag to use for identifying target images
b_tag = '_2020_'
# What tag to use for denoting results
out_tag = '_2018-2020_'
# what change classes do you want to tag with polygons?
global_default_classes = [('added building', 'green'), ('removed building', 'red'), ('uncertain', 'orange')]

# ---------------------------------------------

global_temp_dir = os.path.join(dir_path, 'temp')
if not os.path.exists(global_temp_dir):
    os.mkdir(global_temp_dir)

class SelectionPopUp(QWidget):

    window_width = 500
    window_height = 100
    window_title = 'FlickerTag options selection'
    diff_classes = []

    def __init__(self):
        QWidget.__init__(self)

        self.init_widget_shape_and_position()

        self.auto_button = QPushButton('Automatic mode')
        self.auto_button.clicked.connect(self.start_auto_mode)

        self.manual_button = QPushButton('Manual mode')
        self.manual_button.clicked.connect(self.go_manual)

        self.add_class_button = QPushButton('Add change class')
        self.add_class_button.clicked.connect(self.go_add_change_class)

        self.message_box = QPlainTextEdit()
        self.message_box.insertPlainText('Defined change classes:\n')
        self.message_box.setStyleSheet("color: white; background-color: black; inset grey; min-height: 200px;")
        self.message_box.setLineWidth(3)
        self.message_box.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)

        self.combobox = QComboBox()
        c_count = 0
        for c in ['red', 'green', 'yellow', 'blue', 'magenta', 'cyan', 'orange', 'purple', 'white']:
            self.combobox.addItem(c)
            idx = self.combobox.model().index(c_count, 0)
            self.combobox.model().setData(idx, QColor(c), Qt.BackgroundColorRole)
            c_count += 1
        self.combobox.currentTextChanged.connect(self.on_combobox_changed)
        self.combobox.setStyleSheet("background-color: " + self.combobox.currentText() + "; ")

        self.start_manual_button = QPushButton('Start manual')
        self.start_manual_button.clicked.connect(self.start_manual_mode)

        self.layout().addWidget(self.auto_button,   0, 0, 1, 2)
        self.layout().addWidget(self.manual_button, 1, 0, 1, 2)

    def init_widget_shape_and_position(self):
        """ Initialize the geometry of the widget. """
        self.setMinimumSize(self.window_width, self.window_height)
        self.setLayout(QGridLayout())
        self.setGeometry(0, 0, self.window_width, self.window_height)
        frameGm = self.frameGeometry()
        screen = QApplication.desktop().screenNumber(QApplication.desktop().cursor().pos())
        centerPoint = QApplication.desktop().screenGeometry(screen).center()
        frameGm.moveCenter(centerPoint)
        self.move(frameGm.topLeft())
        self.setWindowTitle(self.window_title)

    def start_auto_mode(self):
        """ Start FickerTag in automatic mode. """
        self.diff_classes = global_default_classes
        gui = FlickerTag_GUI(global_a_dir, global_b_dir, global_out_dir, self.diff_classes, automatic_mode=True)
        gui.show()
        self.close()

    def go_manual(self):
        """ Open manual options in SelectionPopUp. """
        self.window_height = int(self.window_width/1.5)
        self.setMinimumSize(self.window_width, self.window_height)
        if self.diff_classes == []:
            self.manual_button.setText('Reset')
            self.layout().addWidget(self.add_class_button,      2, 0, 1, 1)
            self.layout().addWidget(self.message_box,           3, 0, 1, 2)
            self.layout().addWidget(self.combobox,              2, 1, 1, 1)
            self.layout().addWidget(self.start_manual_button,   4, 0, 1, 2)
        else:
            self.diff_classes = []
            self.message_box.clear()
            self.message_box.insertPlainText('Defined change classes:\n')

    def start_manual_mode(self):
        """ Start FickerTag in manual mode. """
        if len(self.diff_classes) > 0:
            gui = FlickerTag_GUI(global_a_dir, global_b_dir, global_out_dir, self.diff_classes)
            gui.show()
            self.close()

    def on_combobox_changed(self):
        """ Set the color of the combobox when changed. """
        self.combobox.setStyleSheet("background-color: " + self.combobox.currentText() + "; ")

    def go_add_change_class(self):
        """ Open input dialog and add new change class with color corresponding to the combobox. """
        c_text, ok = QInputDialog.getText(self, 'Add change class', 'Class tag:')
        if ok and c_text != '':
            self.message_box.clear()
            self.message_box.insertPlainText('Defined change classes:\n')
            self.diff_classes.append((c_text, self.combobox.currentText()))
            for c in self.diff_classes:
                self.message_box.insertPlainText(c[0] + ' = ' + c[1] + '\n')


class CustomPolygonDrawPanel(QFrame):

    poly_collection = []            # current set of polygons drawn
    candidate_poly_points = []      # current set of points for candidate polygon
    current_back = None             # current image for display
    poly_class = []                 # the class each current polygon belongs to
    line_thickness = 3.0
    point_thickness = 5.0
    shade_alpha = 40

    def __init__(self, color_dict, current_class):
        super().__init__()
        self.setStyleSheet("background-color: rgb(0,0,0); margin:0px;")
        self.color_dict = color_dict
        self.current_class = current_class

    def clear(self):
        """ Clear all variables and update display. """
        self.poly_collection = []
        self.candidate_poly_points = []
        self.current_back = None
        self.poly_class = []
        self.update()

    def do_undo(self):
        """ First try drop the current candidate polygon points.
        If none listed, then drop last created polygon.
        Then refresh display with current variables."""
        if len(self.candidate_poly_points) > 0:
            self.candidate_poly_points = []
        elif len(self.poly_collection) > 0:
            self.poly_collection = self.poly_collection[:-1]
            self.poly_class = self.poly_class[:-1]
        self.refresh_panel(self.current_back)

    def get_polygons(self):
        """ Return the current set of valid polygons, the dimensions of the display,
        and the class to which each polygon belongs. """
        return self.poly_collection, self.rect().size(), self.poly_class

    def refresh_panel(self, new_back_path=None):
        """ Update the display with the current variables.
        If a new file is given, update the display with it as well."""
        if new_back_path is not None:
            self.current_back = new_back_path
        if self.current_back is not None:
            self.pix = QPixmap(self.current_back).scaled(self.rect().size(), Qt.KeepAspectRatio)
            painter = QPainter(self.pix)
            for p in range(len(self.poly_collection)):
                    the_color = QColor(self.color_dict[self.poly_class[p]])
                    the_color.setAlpha(self.shade_alpha)
                    br = QBrush(the_color)
                    poly_pen = QPen(QColor(self.color_dict[self.poly_class[p]]), self.line_thickness, Qt.SolidLine)
                    painter.setBrush(br)
                    painter.setPen(poly_pen)
                    painter.drawPolygon(self.poly_collection[p])
            point_pen = QPen(QColor(self.color_dict[self.current_class]), self.point_thickness, Qt.SolidLine)
            painter.setPen(point_pen)
            for point in self.candidate_poly_points:
                painter.drawPoint(point)
            self.update()

    def paintEvent(self, event):
        """ Facilitates paint events. """
        if self.current_back:
            painter = QPainter(self)
            painter.drawPixmap(QPoint(), self.pix)

    def mousePressEvent(self, event):
        """ Left mouse button means that the current point is added to candidate points,
        right mouse button means that all current candidate points are added to polygon list."""
        if self.current_back is not None:
            if event.buttons() & Qt.LeftButton:
                self.candidate_poly_points.append(event.pos())
                self.update()
            elif event.buttons() & Qt.RightButton:
                self.poly_collection.append(self.candidate_poly_points)
                self.poly_class.append(self.current_class)
                self.candidate_poly_points = []
                self.update()

    def mouseReleaseEvent(self, event):
        """ Refresh display with current variables when mouse button is released."""
        if self.current_back is not None:
            self.refresh_panel(self.current_back)


class FlickerTag_GUI(QWidget):

    window_width = 1200
    window_height = 900
    path_A = ''                 # path to reference image
    path_B = ''                 # path to target image
    path_OUT = ''               # path to output image
    name_A = ''                 # name of reference file
    name_B = ''                 # name of target file
    name_OUT = ''               # name of output file
    flicker_toggle = True
    window_title = 'FlickerTag'
    max_message_box_lines = 25

    def __init__(self, a_dir, b_dir, out_dir, diff_classes, automatic_mode=False):
        super(FlickerTag_GUI, self).__init__()

        self.diff_classes = diff_classes
        self.auto_mode = automatic_mode
        self.out_dir = out_dir
        self.a_dir = a_dir
        self.b_dir = b_dir

        self.color_dict = {}
        for c in self.diff_classes:
            self.color_dict[c[0]] = c[1]
        self.current_class = self.diff_classes[0][0]

        # init general widget shape and location on screen
        self.init_widget_shape_and_position()

        # init displays
        self.disp_A = self.create_display()
        self.disp_B = self.create_display()
        self.disp_C = self.create_interactive_display()

        # init all buttons
        self.select_A_button = self.create_button('Select reference image',
                                                  partial(self.select_image, True, None),
                                                  True)
        self.select_B_button = self.create_button('Select target image',
                                                  partial(self.select_image, False, None),
                                                  True)
        self.save_button = self.create_button('Save', self.proc_results)
        self.save_path_button = self.create_button('Set save dir',
                                                   self.select_save_path, True)
        self.undo_button = self.create_button('Undo', self.undo)
        self.toggle_button = self.create_button('Toggle', self.do_toggle)
        self.skip_button = self.create_button('Skip', partial(self.proc_results, True))
        if automatic_mode:
            self.reset_button = self.create_button('Load next', self.auto_load)
        else:
            self.reset_button = self.create_button('Reset', self.reset_GUI)

        # init message box
        self.message_box = self.create_message_box()

        # init combobox
        self.combobox = self.create_combobox(self.on_combobox_changed)

        # define GUI layout
        self.layout().addWidget(self.select_A_button,       0, 0, 1, 1)
        self.layout().addWidget(self.disp_A,                1, 0, 1, 1)
        self.layout().addWidget(self.select_B_button,       2, 0, 1, 1)
        self.layout().addWidget(self.disp_B,                3, 0, 1, 1)
        self.layout().addWidget(self.message_box,           1, 3, 3, 1)
        self.layout().addWidget(self.combobox,              0, 1, 1, 1)
        self.layout().addWidget(self.disp_C,                1, 1, 3, 2)
        self.layout().addWidget(self.undo_button,           4, 1, 1, 1)
        self.layout().addWidget(self.reset_button,          4, 0, 1, 1)
        self.layout().addWidget(self.save_button,           4, 2, 1, 1)
        self.layout().addWidget(self.save_path_button,      4, 3, 1, 1)
        self.layout().addWidget(self.toggle_button,         0, 2, 1, 1)
        self.layout().addWidget(self.skip_button,           0, 3, 1, 1)

        self.show()
        if self.auto_mode:
            self.update_message_box('Automatic mode active!')
            self.reset_button.click()

    # ----------------------------
    # Initializing the GUI widgets
    # ----------------------------

    def init_widget_shape_and_position(self):
        """ Initialize the geometry of the widget. """
        self.setMinimumSize(self.window_width, self.window_height)
        self.setLayout(QGridLayout())
        self.setGeometry(0, 0, self.window_width, self.window_height)
        frameGm = self.frameGeometry()
        screen = QApplication.desktop().screenNumber(QApplication.desktop().cursor().pos())
        centerPoint = QApplication.desktop().screenGeometry(screen).center()
        frameGm.moveCenter(centerPoint)
        self.move(frameGm.topLeft())
        self.setWindowTitle(self.window_title)

    def create_button(self, text, function_to_connect, disable_if_auto=False):
        """ Create a new generic button with given parameters. """
        new_button = QPushButton(text)
        new_button.clicked.connect(function_to_connect)
        if self.auto_mode and disable_if_auto:
            new_button.setEnabled(False)
        return new_button

    def create_display(self):
        """ Create a new generic display with given parameters. """
        new_display = QLabel()
        new_display.setAlignment(Qt.AlignCenter)
        new_display.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        new_display.setStyleSheet("background-color: black; inset grey; min-height: 200px;")
        new_display.setLineWidth(3)

        return new_display

    def create_message_box(self):
        """ Create a new generic message box with given parameters. """
        new_message_box = QLabel('Hello!')
        new_message_box.setAlignment(Qt.AlignLeft)
        new_message_box.setStyleSheet("color: limegreen; background-color: black; inset grey; min-height: 200px;")
        new_message_box.setLineWidth(3)
        new_message_box.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        return new_message_box

    def create_interactive_display(self):
        """ Create a new interactive display with given parameters. """
        new_interactive_display = CustomPolygonDrawPanel(self.color_dict, self.current_class)
        new_interactive_display.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        return new_interactive_display

    def create_combobox(self, function_to_connect):
        """ Create a new combobox with given parameters and color options. """
        new_combobox = QComboBox()
        c_count = 0
        for c in self.diff_classes:
            new_combobox.addItem(c[0])
            idx = new_combobox.model().index(c_count, 0)
            new_combobox.model().setData(idx, QColor(c[1]), Qt.BackgroundColorRole)
            c_count += 1
        new_combobox.setStyleSheet("background-color: " + self.color_dict[new_combobox.currentText()] + "; ")
        new_combobox.currentTextChanged.connect(function_to_connect)
        new_combobox.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        return new_combobox

    # ----------------------
    # Housekeeping functions
    # ----------------------

    def update_message_box(self, new_message, text_color='limegreen'):
        """ Update the message box by adding a new line with given message and checking for line cap. """
        current_text = self.message_box.text()
        if current_text.count('\n') > self.max_message_box_lines:
            current_text = current_text[current_text.index('\n') + 1:]
        self.message_box.setText(current_text + '\n - ' + new_message)
        self.message_box.setStyleSheet("color: " + text_color + "; background-color: black; inset grey; min-height: 200px;")

    def reset_GUI(self):
        """ Reset GUI completely in order to load another image pair. """
        self.path_A = ''
        self.path_B = ''
        self.disp_A.clear()
        self.disp_B.clear()
        self.disp_C.clear()
        self.message_box.setStyleSheet(
            "color: limegreen; background-color: black; inset grey; min-height: 200px;")
        self.disp_A.setStyleSheet("background-color: black; "
                             "inset grey; "
                             "min-height: 200px")
        self.disp_B.setStyleSheet("background-color: black; "
                             "inset grey; "
                             "min-height: 200px")
        self.update_message_box('Interface reset.')
        self.save_path_button.setText('Save path (' + self.out_dir + ')')

    def proc_image(self, q_image, a):
        """ Given a QPixmap and boolean, populate one of the two basic displays. """
        if a:
            display_image = q_image.scaled(self.disp_A.width(),
                                           self.disp_A.height(),
                                           Qt.KeepAspectRatio)
            self.disp_A.setPixmap(display_image)
            self.flicker_toggle = True
        else:
            display_image = q_image.scaled(self.disp_B.width(),
                                           self.disp_B.height(),
                                           Qt.KeepAspectRatio)
            self.disp_B.setPixmap(display_image)
            self.flicker_toggle = False

    def select_save_path(self):
        """ Select path for saving images. """
        fname = QFileDialog.getExistingDirectory(self, 'Select Folder',
                                                      directory=self.out_dir,
                                                      options=QFileDialog.DontUseNativeDialog)
        if fname != '':
            self.out_dir = fname
            self.save_path_button.setText('Save path (' + self.out_dir + ')')

    def convert_tif_to_temp_png(self, a, tif_path):
        """ Make a temporary png file of the provided tif file and return that path. """
        new_img_data = gdal.Open(tif_path).ReadAsArray()
        new_img_data = np.moveaxis(new_img_data, 0, -1)
        if a:
            temp_path = os.path.join(global_temp_dir, 'temp_a_path.png')
        else:
            temp_path = os.path.join(global_temp_dir, 'temp_b_path.png')
        cv2.imwrite(temp_path, cv2.cvtColor(new_img_data, cv2.COLOR_BGR2RGB))
        return temp_path

    def do_toggle(self):
        """ Have main display toggle between two selected images if available"""
        if self.flicker_toggle and self.disp_B.pixmap() is not None:
            self.disp_C.refresh_panel(self.path_B)
            self.flicker_toggle = False
            self.select_B_button.setStyleSheet("background-color: blue; ")
            self.select_A_button.setStyleSheet("background-color: white; ")
        elif self.disp_A.pixmap() is not None:
            self.disp_C.refresh_panel(self.path_A)
            self.flicker_toggle = True
            self.select_A_button.setStyleSheet("background-color: blue; ")
            self.select_B_button.setStyleSheet("background-color: white; ")
        else:
            self.update_message_box('No image pair selected.', 'red')

    def undo(self):
        """ Tell the main display to undo the last polygon addition. """
        self.disp_C.do_undo()
        self.update_message_box('Backtracked.')

    def on_combobox_changed(self):
        """ Tell the main display to update it's current class and sets combobox to appropriate color. """
        self.disp_C.current_class = self.combobox.currentText()
        self.combobox.setStyleSheet("background-color: " + self.color_dict[self.combobox.currentText()] + "; ")
        self.disp_C.refresh_panel()

    # --------------
    # core functions
    # --------------

    def select_image(self, a, fname=None):
        """ Update GUI with new image if provided, or have user select one. """

        # if not provided have user select file
        if fname is None:
            if a:
                fname = QFileDialog.getOpenFileName(self, 'Select image A',
                                                    self.a_dir, "Image files (*.jpg *.png *.tif *.tiff)",
                                                    options=QFileDialog.DontUseNativeDialog)
            else:
                fname = QFileDialog.getOpenFileName(self, 'Select image B',
                                                    self.b_dir, "Image files (*.jpg *.png *.tif *.tiff)",
                                                    options=QFileDialog.DontUseNativeDialog)
            fname = fname[0]

        if fname != '':
            # set required parameters according to file path and convert to temp png if required
            if a:
                self.path_A = fname
                self.name_A = fname.split('/')[-1]
                self.a_dir = os.path.dirname(self.path_A)
                if fname.endswith('.tif') or fname.endswith('.tiff'):
                    self.path_A = self.convert_tif_to_temp_png(a, fname)
                go_path = self.path_A
            else:
                self.path_B = fname
                self.name_B = fname.split('/')[-1]
                self.name_OUT = self.name_B
                self.b_dir = os.path.dirname(self.path_B)
                if fname.endswith('.tif') or fname.endswith('.tiff'):
                    self.path_B = self.convert_tif_to_temp_png(a, fname)
                go_path = self.path_B

            # updated related displays
            image = QPixmap(go_path)
            self.disp_C.refresh_panel(go_path)
            self.proc_image(image, a)

            if a:
                self.update_message_box('Reference selected.')
            else:
                self.update_message_box('Target selected.')

        else:
            self.update_message_box('No image selected.', 'red')

    def auto_load(self):
        """ Automatically load the next image pair and press relevant buttons.

        Images are matched if they are identical except for the presence of a_tag or b_tag.
        Corresponding output files are names identically except for the present of out_tag.

        """

        a_files = [f for f in os.listdir(self.a_dir) if a_tag in f]
        b_files = [f for f in os.listdir(self.b_dir) if b_tag in f]
        out_files = [f for f in os.listdir(self.out_dir)]

        done_count = 0      # how many valid image pairs already have corresponding results
        to_do_count = 0     # how many valid image pairs do not have corresponding results yet
        unknown_count = 0   # how many images do not seem to belong in a pair
        to_compare = []
        for a_f in a_files:
            a_f_split = a_f.split(a_tag)
            if len(a_f_split) == 2:
                target_name = a_f_split[0] + b_tag + a_f_split[1]
                out_name = a_f_split[0] + out_tag + a_f_split[1]
            else:
                target_name = a_f_split[0] + b_tag
                for a in a_f_split[1:]:
                    target_name += a + a_tag
                target_name = target_name[:-len(a_tag)]
                out_name = target_name.split(b_tag)[0] + out_tag + target_name.split(b_tag)[1]
            out_name = os.path.splitext(out_name)[0] + '.pickle'
            if target_name in b_files and out_name not in out_files:
                to_compare.append([os.path.join(self.a_dir, a_f),
                                   os.path.join(self.b_dir, target_name),
                                   os.path.join(self.out_dir, out_name)])
                to_do_count += 1
            elif target_name in b_files:
                done_count += 1
            else:
                unknown_count += 1

        if len(to_compare) == 0:
            self.update_message_box('No more images to compare.')
            self.reset_GUI()
        else:
            self.update_message_box('TO DO: ' + str(to_do_count) + '; done: ' + str(done_count) + '; unknown: ' + str(unknown_count))
            self.select_image(True, os.path.join(self.a_dir, to_compare[0][0]))
            self.select_image(False, os.path.join(self.b_dir, to_compare[0][1]))
            self.path_OUT = to_compare[0][2]

    def proc_results(self, skipped=False):
        """ Request results from main display and save. Also reset and load next if in auto mode."""
        if not self.auto_mode:
            example_id = self.name_OUT.split('/')[-1]
            example_id = example_id.split('.')[0]
            out_id = example_id.replace(b_tag, out_tag)
            default_path = os.path.join(self.out_dir, out_id + '.pickle')
            fname = QFileDialog.getSaveFileName(directory=default_path, options=QFileDialog.DontUseNativeDialog)
            self.path_OUT = fname[0]

        if self.path_B == '':
            self.update_message_box('WARNING!\n' + 'No target selected!', 'red')
        elif self.path_OUT != '':
            if skipped:
                results = 'skipped by annotator'
            else:
                polygons, r_size, polygon_class = self.disp_C.get_polygons()
                scaled_polygons, image_height, image_width = self.get_scaled_polygons(polygons, r_size)
                results = [[scaled_polygons[p], polygon_class[p]] for p in range(len(scaled_polygons))]
                self.update_message_box(' - Saved with ' + str(len(polygon_class)) + ' polygons.')
            with open(self.path_OUT, 'wb') as handle:
                pickle.dump(results, handle, protocol=pickle.HIGHEST_PROTOCOL)
            self.display_results(self.path_OUT)

            if self.auto_mode:
                self.reset_GUI()
                self.auto_load()

    def get_scaled_polygons(self, polygons, r_size):
        """ Given the resulting polygons and relative size of display panel, scale them to actual image size. """

        def lin_trans(val, old_min, old_max, new_min, new_max):
            return new_min + (new_max - new_min) * ((val - old_min) / (old_max - old_min))

        polygons = [[[r.x(), r.y()] for r in p] for p in polygons]
        image = QPixmap(self.path_B)
        image_width = image.width()
        image_height = image.height()
        panel_width = r_size.width()
        panel_height = r_size.height()
        panel_width, panel_height = min(panel_width, panel_height), min(panel_width, panel_height)

        scaled_polygons = []
        for poly in polygons:
            poly = np.array(poly)
            for point in poly:
                point[0] = lin_trans(point[0], old_min=0, old_max=panel_width, new_min=0, new_max=image_width)
                point[1] = lin_trans(point[1], old_min=0, old_max=panel_height, new_min=0, new_max=image_height)
            scaled_polygons.append(poly)

        return scaled_polygons, image_height, image_width

    def display_results(self, saved_pickle_file):

        """Given the path to the saved pickle. Open it and create an illustrative difference map of it.
        Display it on the main display, if not skipped. """

        with open(saved_pickle_file, 'rb') as handle:
            results = pickle.load(handle)

        if results != 'skipped by annotator':
            image = QPixmap(self.path_B)
            disc_map = np.zeros(shape=(image.height(), image.width(), 3))
            for polygon in results:
                poly_class = polygon[1]
                poly_points = polygon[0]
                the_color = colors.to_rgba(self.color_dict[poly_class])
                cv2.fillPoly(disc_map, pts=np.int32([poly_points]), color=the_color)

            disc_map = 125 * disc_map
            disc_map = np.float32(disc_map)
            disc_map = cv2.cvtColor(disc_map, cv2.COLOR_BGR2RGB)
            temp_save_path = os.path.join(global_temp_dir, 'temp_results.png')
            cv2.imwrite(temp_save_path, disc_map)
            self.disp_C.refresh_panel(temp_save_path)


def main():
    app = QApplication(sys.argv)
    popgui = SelectionPopUp()
    popgui.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()