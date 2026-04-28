// Adds column2, column3,... to output
import {app} from "../../scripts/app.js"

class Spreadsheet2Video {
//  onNodeCreated(side, slot, connect, link_info, output) {

  onNodeCreated(graphNode) {
    return this.addRemoveOutput(graphNode, false);
  }
  onConnectionsChange(side, slot, connect, link_info /*, output */) {
    if(!link_info?.origin_id) {
      return;
    }

    const graphNode = app.graph.getNodeById(link_info.origin_id);
    if(!graphNode) {
      return;
    }
    this.addRemoveOutput(graphNode, true);
  }

  addRemoveOutput(graphNode, onlyExisting) {
    if(!graphNode) {
      return;
    }

    let columnsCount = 0;
    let columnLinkedMax = 0;
    let columnMax = 0;
    let lastColumn = 1;
    const outputsByColumn = [];
    for(const output of graphNode.outputs) {
      const m = /^COLUMN(\d+)$/.exec(output.name);
      if(!m) {
        continue;
      }
      const column = parseInt(m[1]);
      if(output.links && column >= columnLinkedMax) {
        columnLinkedMax = column;
      }
      if(column >= columnMax) {
        columnMax = column;
      }
      outputsByColumn[column] = columnsCount;
      if ((lastColumn+1) != column) {
        console.error(`Spreadsheet2VideoInputImage.  Column mismatch. Expected COLUMN${lastColumn+1}, found: ${column}`);
      }
      ++columnsCount;
      lastColumn = column;
    }
    if(onlyExisting && columnsCount === 0) {
      return false;
    }

    let columnMaxWanted = Math.ceil((columnLinkedMax+3)/2)*2;
    const removeSlotIndex = [];
    for(let c = columnMaxWanted; c<outputsByColumn.length; ++c) {
      const slotIndex = outputsByColumn[c];
      if(slotIndex !== undefined) {
        removeSlotIndex.push(slotIndex);
      }
    }

    for(let c = 2; c<=columnMaxWanted; ++c) {
      const slotIndex = outputsByColumn[c];
      if(slotIndex === undefined) {
        graphNode.addOutput(`COLUMN${c}`, null);
      }
    }
    return true;
  }

  // onWidgetChanged(name, v, oldV, widget) { }

  init() {
    const t=this;
    app.registerExtension({
      name: "Spreadsheet2Video",
      async beforeRegisterNodeDef(nodeType /*, nodeData, app */) {
        if (nodeType.comfyClass === "Spreadsheet2VideoInputImage") {
          const onConnectionsChange = nodeType.prototype.onConnectionsChange;
          nodeType.prototype.onConnectionsChange = function (
            side, slot, connect, link_info, output
          ) {
            // biome-ignore lint/style/noArguments: Using arguments with apply()
            const r = onConnectionsChange?.apply(this, arguments);
            try {
              t.onConnectionsChange(side, slot, connect, link_info, output);
            } catch(e) {
              console.error('S2V.onConnectionsChange crash:', e);
            }
            return r;
          }

          const onNodeCreated = nodeType.prototype.onNodeCreated;
          nodeType.prototype.onNodeCreated = function (
          ) {
            // biome-ignore lint/style/noArguments: Using arguments with apply()
            const r = onNodeCreated?.apply(this, arguments);
            try {
              t.onNodeCreated(this);
            } catch(e) {
              console.error('S2V.onNodeCreated crash:', e);
            }
            return r;
          }

          /*
          const onWidgetChanged = nodeType.prototype.onWidgetChanged;
          nodeType.prototype.onWidgetChanged = function (name, v, oldV, widget) {
            // biome-ignore lint/style/noArguments: Using arguments with apply()
            const r = onWidgetChanged?.apply(this, arguments);
            t.onWidgetChanged(name, v, oldV, widget);
            return r;
          };
          */
        }
      },
    });
  }
}
new Spreadsheet2Video().init();

