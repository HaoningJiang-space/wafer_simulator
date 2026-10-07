# Python modules
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle


# Custom modules




colors = {
        "compute" : "lightblue",
        "interconnect" : "lightgreen",
        }



def visualize(inputs):
    print("Creating visualization...")

    name = inputs["name"]
    chiplets = inputs["chiplets"]
    placement = inputs["placement"]
    links = inputs["links"]

    fig, ax = plt.subplots()
    ax.set_aspect('equal')

    minx, maxx = 0, 0
    miny, maxy = 0, 0

    for cid, chiplet_desc in enumerate(placement["chiplets"]):
        chiplet = chiplets[chiplet_desc["name"]]
        w, h = chiplet["dimensions"]["x"] * 0.95, chiplet["dimensions"]["y"] * 0.95
        x, y, = chiplet_desc["position"]["x"] - w/2, chiplet_desc["position"]["y"] - h/2
        typ = chiplet["type"]
        col = colors[typ]
        rect = Rectangle((x, y), w, h, facecolor=col, edgecolor='black', alpha=1.0 - 0.4 * chiplet_desc["layer"])
        ax.add_patch(rect)
        circ = plt.Circle((x + w/2, y + h/2), (w+h) / 20, color='black') # Central router
        ax.add_patch(circ)
        # Update bounds
        minx = min(minx, x - w/2)
        maxx = max(maxx, x + w/2)
        miny = min(miny, y - h/2)
        maxy = max(maxy, y + h/2)
        # Add ID
        ax.text(x + w/2, y + h/2, str(cid), color='black', fontsize=12, ha='center', va='center')


    for link in links:
        src = placement["chiplets"][link["src"]]
        dst = placement["chiplets"][link["dst"]]
        x1, y1 = src["position"]["x"], src["position"]["y"]
        x2, y2 = dst["position"]["x"], dst["position"]["y"]
        ax.plot([x1, x2], [y1, y2], color='black', linewidth=1)

    ax.set_xlim(minx - 10, maxx + 10)
    ax.set_ylim(miny - 10, maxy + 10)

    plt.savefig("rapidchiplet/visualizations/" + name + ".pdf")
