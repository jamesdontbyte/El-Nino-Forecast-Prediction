import numpy as np

from app.layer2.municipal_rain import choose_pixels, point_inside

# A 2 x 2 grid of real-size squares (0.05 degrees). The top-right square is sea.
LATS = np.array([0.025, 0.075])
LONS = np.array([0.025, 0.075])
LAND = np.array([[True, True], [True, False]])


def square(low_x, low_y, size):
    return [[low_x, low_y], [low_x + size, low_y], [low_x + size, low_y + size], [low_x, low_y + size],
            [low_x, low_y]]


def test_point_inside_stays_inside_a_c_shape():
    # A "C" shape whose vertex mean falls in the open gap, outside the shape.
    c_shape = {"type": "Polygon", "coordinates": [[[0, 0], [3, 0], [3, 1], [1, 1], [1, 2], [3, 2], [3, 3],
                                                   [0, 3], [0, 0]]]}
    x, y = point_inside(c_shape)
    assert x < 1 or y < 1 or y > 2  # strictly inside one of the three arms, not on an edge


def test_small_shape_takes_the_nearest_land_square_or_none():
    tiny = {"type": "Polygon", "coordinates": [square(0.03, 0.03, 0.01)]}  # no square centre inside
    mask, rule = choose_pixels(tiny, LATS, LONS, LAND)
    assert rule == "nearest" and mask.sum() == 1 and mask[0, 0]

    far = {"type": "Polygon", "coordinates": [square(0.2, 0.2, 0.01)]}  # nearest land is beyond the cap
    mask, rule = choose_pixels(far, LATS, LONS, LAND)
    assert rule == "none" and not mask.any()

    big = {"type": "Polygon", "coordinates": [square(0, 0, 0.1)]}  # covers all four centres
    mask, rule = choose_pixels(big, LATS, LONS, LAND)
    assert rule == "inside" and mask.sum() == 3  # the sea square is left out
