from rotary_enc import Rotary

class Menu:
    def __init__(self, menu_list, total_lines):
        self.current_line = 1
        self.total_lines = total_lines
        self.items = menu_list
        self.shift = 0
    
    def show(self):
        return self.items[self.shift : self.shift + self.total_lines]
    
    def update(self, menu_list):
        self.items = menu_list
        self.show()
    
    def next(self):                                     
        if self.current_line < self.total_lines:
            self.current_line += 1
        elif self.shift + self.total_lines < len(self.items):
            self.shift += 1
        return self.items[self.shift : self.shift + self.total_lines]
    
    def previous(self):
        if self.current_line == 0:
            self.current_line = 1
        elif self.current_line > 1:
            self.current_line -= 1
        elif self.shift > 0:
            self.shift -= 1
            
        return self.items[self.shift : self.shift + self.total_lines]


############### END OF CLASS ################
    
