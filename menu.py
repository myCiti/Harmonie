from rotary_enc import Rotary

class Menu:
    def __init__(self, menu_list, total_lines):
        self._current_line = 1
        self._current_level = 1
        self._total_lines = total_lines
        self._menu_list = menu_list
        self._shift = 0
    
    def show(self):
        return self._menu_list[self._shift : self._shift + self._total_lines]
    
    def next(self):                                     
        if self._current_line < self._total_lines:
            self._current_line += 1
        elif self._shift + self._total_lines < len(self._menu_list):
            self._shift += 1
        return self._menu_list[self._shift : self._shift + self._total_lines]
    
    def previous(self):
        if self._current_line == 0:
            self._current_line = 1
        elif self._current_line > 1:
            self._current_line -= 1
        elif self._shift > 0:
            self._shift -= 1
            
        return self._menu_list[self._shift : self._shift + self._total_lines]


############### END OF CLASS ################
    
