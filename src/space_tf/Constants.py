import numpy as np

def R_x(q): return np.matrix([[1, 0, 0],[0, np.cos(q), -np.sin(q)],[0, np.sin(q), np.cos(q)]])
def R_y(q): return np.matrix([[np.cos(q), 0, np.sin(q)],[0, 1, 0],[-np.sin(q), 0, np.cos(q)]])
def R_z(q): return np.matrix([[np.cos(q), -np.sin(q), 0],[np.sin(q), np.cos(q), 0],[0, 0, 1]])


class Constants:
    mu_earth = 3.986004418e14/1e9   # [km^3]/[s^2], thus divided by 1e9
