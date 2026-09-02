/**
 * W1-04 spike — hand-authored DXF fixtures.
 *
 * The DXF below is written group code by group code on purpose: the spike has to
 * know exactly which handles and entities exist so that the `dxfOut()` round-trip
 * table (ADR-0002 converter tier 2) can be checked against a known truth.
 *
 * Outputs
 *   fixtures/F-spike-r2018.dxf   AC1032, UTF-8            (primary fixture)
 *   fixtures/F-spike-r2000.dxf   AC1015, CP949 bytes      (encoding variant)
 *   fixtures/F-spike-truth.json  expected handles/counts
 *
 * Run: npm run fixtures
 */
import { mkdirSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import iconv from 'iconv-lite';

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = resolve(HERE, '..', 'fixtures');

/** Emit a DXF group pair list from a flat [code, value, code, value, ...] array. */
const g = (...pairs) => {
  const lines = [];
  for (let i = 0; i < pairs.length; i += 2) {
    lines.push(String(pairs[i]));
    lines.push(String(pairs[i + 1]));
  }
  return lines;
};

// --------------------------------------------------------------------------
// Handle plan. Kept explicit so the round-trip check can assert preservation.
// --------------------------------------------------------------------------
const H = {
  // symbol tables
  tblBlockRecord: '1',
  tblLayer: '2',
  tblStyle: '3',
  tblLtype: '5',
  tblView: '6',
  tblUcs: '7',
  tblVport: '8',
  tblAppId: '9',
  tblDimStyle: 'A',
  // objects
  dictRoot: 'C',
  dictGroup: 'D',
  dictLayout: 'E',
  // table records
  layer0: '10',
  layerWall: '11',
  layerText: '12',
  layerHatch: '13',
  layerDim: '14',
  ltByBlock: '15',
  ltByLayer: '16',
  ltContinuous: '17',
  ltDashed: '18',
  styStandard: '19',
  styHangul: '1A',
  appAcad: '1B',
  dimStandard: '1C',
  vportActive: '1D',
  brModel: '1E',
  brPaper: '1F',
  brTitle: '20',
  brD1: '21',
  // block begin/end
  blkModel: '22',
  blkModelEnd: '23',
  blkPaper: '24',
  blkPaperEnd: '25',
  blkTitle: '26',
  blkTitleEnd: '27',
  blkD1: '28',
  blkD1End: '29',
  // entities inside blocks
  titlePline: '2A',
  titleAttdef: '2B',
  d1DimLine: '2C',
  d1Ext1: '2D',
  d1Ext2: '2E',
  d1Text: '2F',
  // layouts
  layoutModel: '30',
  layoutPaper: '31',
  // model space entities
  eLine: '100',
  ePline: '101',
  eCircle: '102',
  eArc: '103',
  eText: '104',
  eMText: '105',
  eInsert: '106',
  eAttrib: '107',
  eSeqEnd: '108',
  eHatch: '109',
  eDim: '10A',
  // paper space entities
  pViewportMain: '200',
  pViewport2: '201',
  pLine: '202',
};

const KO = {
  text: '대명건설 도면',
  mtextLine1: '지하 1층 평면도',
  mtextLine2: '축척 1:100',
  mtextLine3: '검토자 홍길동',
  layerDim: '치수',
  attTag: 'TITLE', // DXF attribute tags must stay ASCII (AutoCAD restriction)
  attPrompt: '도면 제목',
  attValue: '대명건설 신축공사',
  dimText: '100',
};

// --------------------------------------------------------------------------
// HEADER
// --------------------------------------------------------------------------
const header = (acadver, codepage) =>
  g(
    0, 'SECTION',
    2, 'HEADER',
    9, '$ACADVER', 1, acadver,
    9, '$DWGCODEPAGE', 3, codepage,
    9, '$HANDSEED', 5, 'FFFF',
    9, '$INSBASE', 10, '0.0', 20, '0.0', 30, '0.0',
    9, '$EXTMIN', 10, '-60.0', 20, '-60.0', 30, '0.0',
    9, '$EXTMAX', 10, '260.0', 20, '160.0', 30, '0.0',
    9, '$LIMMIN', 10, '0.0', 20, '0.0',
    9, '$LIMMAX', 10, '420.0', 20, '297.0',
    9, '$INSUNITS', 70, 4,
    9, '$MEASUREMENT', 70, 1,
    9, '$LUNITS', 70, 2,
    9, '$LUPREC', 70, 4,
    9, '$TILEMODE', 70, 1,
    9, '$PDMODE', 70, 0,
    9, '$CLAYER', 8, '0',
    9, '$TEXTSTYLE', 7, 'Standard',
    9, '$DIMSTYLE', 2, 'Standard',
    9, '$CELTYPE', 6, 'ByLayer',
    9, '$CECOLOR', 62, 256,
    0, 'ENDSEC'
  );

// --------------------------------------------------------------------------
// TABLES
// --------------------------------------------------------------------------
const layerRec = (handle, name, color, ltype, lw) =>
  g(
    0, 'LAYER',
    5, handle,
    330, H.tblLayer,
    100, 'AcDbSymbolTableRecord',
    100, 'AcDbLayerTableRecord',
    2, name,
    70, 0,
    62, color,
    6, ltype,
    370, lw,
    290, 1
  );

const ltypeRec = (handle, name, desc, extra = []) =>
  g(
    0, 'LTYPE',
    5, handle,
    330, H.tblLtype,
    100, 'AcDbSymbolTableRecord',
    100, 'AcDbLinetypeTableRecord',
    2, name,
    70, 0,
    3, desc,
    72, 65,
    ...extra
  );

const tables = (acadver) => {
  const isR2018 = acadver === 'AC1032';
  return [
    ...g(0, 'SECTION', 2, 'TABLES'),

    // ---- VPORT
    ...g(0, 'TABLE', 2, 'VPORT', 5, H.tblVport, 100, 'AcDbSymbolTable', 70, 1),
    ...g(
      0, 'VPORT', 5, H.vportActive, 330, H.tblVport,
      100, 'AcDbSymbolTableRecord', 100, 'AcDbViewportTableRecord',
      2, '*Active', 70, 0,
      10, '0.0', 20, '0.0', 11, '1.0', 21, '1.0',
      12, '100.0', 22, '50.0', 13, '0.0', 23, '0.0',
      14, '10.0', 24, '10.0', 15, '10.0', 25, '10.0',
      16, '0.0', 26, '0.0', 36, '1.0',
      17, '0.0', 27, '0.0', 37, '0.0',
      40, '297.0', 41, '1.5', 42, '50.0', 43, '0.0', 44, '0.0',
      50, '0.0', 51, '0.0',
      71, 0, 72, 100, 73, 1, 74, 3, 75, 0, 76, 0, 77, 0, 78, 0
    ),
    ...g(0, 'ENDTAB'),

    // ---- LTYPE
    ...g(0, 'TABLE', 2, 'LTYPE', 5, H.tblLtype, 100, 'AcDbSymbolTable', 70, 4),
    ...ltypeRec(H.ltByBlock, 'ByBlock', '', g(73, 0, 40, '0.0')),
    ...ltypeRec(H.ltByLayer, 'ByLayer', '', g(73, 0, 40, '0.0')),
    ...ltypeRec(H.ltContinuous, 'Continuous', 'Solid line', g(73, 0, 40, '0.0')),
    ...ltypeRec(
      H.ltDashed, 'DASHED', 'Dashed __ __ __ __',
      g(73, 2, 40, '15.0', 49, '12.0', 74, 0, 49, '-3.0', 74, 0)
    ),
    ...g(0, 'ENDTAB'),

    // ---- LAYER (0 + three working layers + one Korean-named layer)
    ...g(0, 'TABLE', 2, 'LAYER', 5, H.tblLayer, 100, 'AcDbSymbolTable', 70, 5),
    ...layerRec(H.layer0, '0', 7, 'Continuous', -3),
    ...layerRec(H.layerWall, 'A-WALL', 3, 'Continuous', 25),
    ...layerRec(H.layerText, 'A-TEXT', 2, 'Continuous', 13),
    ...layerRec(H.layerHatch, 'A-HATCH', 1, 'DASHED', 9),
    ...layerRec(H.layerDim, KO.layerDim, 4, 'Continuous', 9),
    ...g(0, 'ENDTAB'),

    // ---- STYLE (Standard + a Korean SHX big-font style)
    ...g(0, 'TABLE', 2, 'STYLE', 5, H.tblStyle, 100, 'AcDbSymbolTable', 70, 2),
    ...g(
      0, 'STYLE', 5, H.styStandard, 330, H.tblStyle,
      100, 'AcDbSymbolTableRecord', 100, 'AcDbTextStyleTableRecord',
      2, 'Standard', 70, 0, 40, '0.0', 41, '1.0', 50, '0.0', 71, 0, 42, '2.5',
      3, 'txt.shx', 4, ''
    ),
    ...g(
      0, 'STYLE', 5, H.styHangul, 330, H.tblStyle,
      100, 'AcDbSymbolTableRecord', 100, 'AcDbTextStyleTableRecord',
      2, 'HANGUL', 70, 0, 40, '0.0', 41, '0.9', 50, '0.0', 71, 0, 42, '2.5',
      3, 'txt.shx', 4, 'whgtxt.shx'
    ),
    ...g(0, 'ENDTAB'),

    // ---- VIEW / UCS (empty but present; some readers expect the table headers)
    ...g(0, 'TABLE', 2, 'VIEW', 5, H.tblView, 100, 'AcDbSymbolTable', 70, 0, 0, 'ENDTAB'),
    ...g(0, 'TABLE', 2, 'UCS', 5, H.tblUcs, 100, 'AcDbSymbolTable', 70, 0, 0, 'ENDTAB'),

    // ---- APPID
    ...g(0, 'TABLE', 2, 'APPID', 5, H.tblAppId, 100, 'AcDbSymbolTable', 70, 1),
    ...g(
      0, 'APPID', 5, H.appAcad, 330, H.tblAppId,
      100, 'AcDbSymbolTableRecord', 100, 'AcDbRegAppTableRecord', 2, 'ACAD', 70, 0
    ),
    ...g(0, 'ENDTAB'),

    // ---- DIMSTYLE (record handle uses group code 105, not 5)
    ...g(
      0, 'TABLE', 2, 'DIMSTYLE', 5, H.tblDimStyle,
      100, 'AcDbSymbolTable', 70, 1, 100, 'AcDbDimStyleTable', 71, 0
    ),
    ...g(
      0, 'DIMSTYLE', 105, H.dimStandard, 330, H.tblDimStyle,
      100, 'AcDbSymbolTableRecord', 100, 'AcDbDimStyleTableRecord',
      2, 'Standard', 70, 0,
      40, '1.0', 41, '2.5', 42, '0.625', 43, '3.75', 44, '1.25',
      140, '2.5', 141, '2.5', 147, '0.625',
      73, 0, 74, 0, 77, 1, 78, 8,
      171, 3, 172, 1, 271, 4, 272, 4, 274, 3, 278, 44,
      340, H.styStandard
    ),
    ...g(0, 'ENDTAB'),

    // ---- BLOCK_RECORD
    ...g(0, 'TABLE', 2, 'BLOCK_RECORD', 5, H.tblBlockRecord, 100, 'AcDbSymbolTable', 70, 4),
    ...g(
      0, 'BLOCK_RECORD', 5, H.brModel, 330, H.tblBlockRecord,
      100, 'AcDbSymbolTableRecord', 100, 'AcDbBlockTableRecord',
      2, '*Model_Space', 340, H.layoutModel, 70, 0, 280, 1, 281, 0
    ),
    ...g(
      0, 'BLOCK_RECORD', 5, H.brPaper, 330, H.tblBlockRecord,
      100, 'AcDbSymbolTableRecord', 100, 'AcDbBlockTableRecord',
      2, '*Paper_Space', 340, H.layoutPaper, 70, 0, 280, 1, 281, 0
    ),
    ...g(
      0, 'BLOCK_RECORD', 5, H.brTitle, 330, H.tblBlockRecord,
      100, 'AcDbSymbolTableRecord', 100, 'AcDbBlockTableRecord',
      2, 'TITLEBLK', 70, 0, 280, 1, 281, 0
    ),
    ...g(
      0, 'BLOCK_RECORD', 5, H.brD1, 330, H.tblBlockRecord,
      100, 'AcDbSymbolTableRecord', 100, 'AcDbBlockTableRecord',
      2, '*D1', 70, 0, 280, 1, 281, 0
    ),
    ...g(0, 'ENDTAB'),

    ...g(0, 'ENDSEC'),
    ...(isR2018 ? [] : []),
  ];
};

// --------------------------------------------------------------------------
// BLOCKS
// --------------------------------------------------------------------------
const blockBegin = (handle, ownerBtr, name, layer = '0') =>
  g(
    0, 'BLOCK', 5, handle, 330, ownerBtr,
    100, 'AcDbEntity', 8, layer,
    100, 'AcDbBlockBegin',
    2, name, 70, 0,
    10, '0.0', 20, '0.0', 30, '0.0',
    3, name, 1, ''
  );

const blockEnd = (handle, ownerBtr, layer = '0') =>
  g(0, 'ENDBLK', 5, handle, 330, ownerBtr, 100, 'AcDbEntity', 8, layer, 100, 'AcDbBlockEnd');

const line = (handle, owner, layer, x1, y1, x2, y2, space = 0) =>
  g(
    0, 'LINE', 5, handle, 330, owner,
    100, 'AcDbEntity', 67, space, 8, layer,
    100, 'AcDbLine',
    10, x1, 20, y1, 30, '0.0',
    11, x2, 21, y2, 31, '0.0'
  );

const blocks = () => [
  ...g(0, 'SECTION', 2, 'BLOCKS'),

  // *Model_Space
  ...blockBegin(H.blkModel, H.brModel, '*Model_Space'),
  ...blockEnd(H.blkModelEnd, H.brModel),

  // *Paper_Space
  ...blockBegin(H.blkPaper, H.brPaper, '*Paper_Space'),
  ...blockEnd(H.blkPaperEnd, H.brPaper),

  // TITLEBLK — a rectangle plus one attribute definition
  ...blockBegin(H.blkTitle, H.brTitle, 'TITLEBLK'),
  ...g(
    0, 'LWPOLYLINE', 5, H.titlePline, 330, H.brTitle,
    100, 'AcDbEntity', 8, '0',
    100, 'AcDbPolyline',
    90, 4, 70, 1, 43, '0.0',
    10, '0.0', 20, '0.0',
    10, '60.0', 20, '0.0',
    10, '60.0', 20, '20.0',
    10, '0.0', 20, '20.0'
  ),
  ...g(
    0, 'ATTDEF', 5, H.titleAttdef, 330, H.brTitle,
    100, 'AcDbEntity', 8, 'A-TEXT',
    100, 'AcDbText',
    10, '3.0', 20, '6.0', 30, '0.0',
    40, '5.0',
    1, KO.attValue,
    7, 'HANGUL',
    100, 'AcDbAttributeDefinition',
    3, KO.attPrompt,
    2, KO.attTag,
    70, 0, 73, 0, 74, 0
  ),
  ...blockEnd(H.blkTitleEnd, H.brTitle),

  // *D1 — anonymous block that carries the linear dimension geometry
  ...blockBegin(H.blkD1, H.brD1, '*D1', KO.layerDim),
  ...line(H.d1DimLine, H.brD1, KO.layerDim, '0.0', '-20.0', '100.0', '-20.0'),
  ...line(H.d1Ext1, H.brD1, KO.layerDim, '0.0', '-2.0', '0.0', '-22.0'),
  ...line(H.d1Ext2, H.brD1, KO.layerDim, '100.0', '-2.0', '100.0', '-22.0'),
  ...g(
    0, 'MTEXT', 5, H.d1Text, 330, H.brD1,
    100, 'AcDbEntity', 8, KO.layerDim,
    100, 'AcDbMText',
    10, '50.0', 20, '-18.0', 30, '0.0',
    40, '5.0', 41, '0.0', 46, '0.0',
    71, 5, 72, 5,
    1, KO.dimText,
    7, 'Standard',
    11, '1.0', 21, '0.0', 31, '0.0',
    73, 1, 44, '1.0'
  ),
  ...blockEnd(H.blkD1End, H.brD1, KO.layerDim),

  ...g(0, 'ENDSEC'),
];

// --------------------------------------------------------------------------
// ENTITIES
// --------------------------------------------------------------------------
const entities = () => [
  ...g(0, 'SECTION', 2, 'ENTITIES'),

  // 1. LINE
  ...line(H.eLine, H.brModel, 'A-WALL', '0.0', '0.0', '200.0', '0.0'),

  // 2. LWPOLYLINE — closed rectangle, one bulged segment
  ...g(
    0, 'LWPOLYLINE', 5, H.ePline, 330, H.brModel,
    100, 'AcDbEntity', 8, 'A-WALL',
    100, 'AcDbPolyline',
    90, 4, 70, 1, 43, '0.0',
    10, '0.0', 20, '0.0',
    10, '200.0', 20, '0.0',
    10, '200.0', 20, '100.0', 42, '0.5',
    10, '0.0', 20, '100.0'
  ),

  // 3. CIRCLE
  ...g(
    0, 'CIRCLE', 5, H.eCircle, 330, H.brModel,
    100, 'AcDbEntity', 8, 'A-WALL',
    100, 'AcDbCircle',
    10, '50.0', 20, '50.0', 30, '0.0',
    40, '20.0'
  ),

  // 4. ARC
  ...g(
    0, 'ARC', 5, H.eArc, 330, H.brModel,
    100, 'AcDbEntity', 8, 'A-WALL',
    100, 'AcDbCircle',
    10, '150.0', 20, '50.0', 30, '0.0',
    40, '25.0',
    100, 'AcDbArc',
    50, '0.0', 51, '90.0'
  ),

  // 5. TEXT — Korean, uses the SHX big-font style
  ...g(
    0, 'TEXT', 5, H.eText, 330, H.brModel,
    100, 'AcDbEntity', 8, 'A-TEXT',
    100, 'AcDbText',
    10, '10.0', 20, '110.0', 30, '0.0',
    40, '8.0',
    1, KO.text,
    7, 'HANGUL',
    72, 0, 11, '0.0', 21, '0.0', 31, '0.0',
    100, 'AcDbText', 73, 0
  ),

  // 6. MTEXT — Korean, \P line breaks and one inline colour code
  ...g(
    0, 'MTEXT', 5, H.eMText, 330, H.brModel,
    100, 'AcDbEntity', 8, 'A-TEXT',
    100, 'AcDbMText',
    10, '10.0', 20, '145.0', 30, '0.0',
    40, '6.0', 41, '120.0', 46, '0.0',
    71, 1, 72, 5,
    1, `${KO.mtextLine1}\\P${KO.mtextLine2}\\P{\\C1;${KO.mtextLine3}}`,
    7, 'Standard',
    11, '1.0', 21, '0.0', 31, '0.0',
    73, 1, 44, '1.0'
  ),

  // 7. INSERT + ATTRIB + SEQEND
  ...g(
    0, 'INSERT', 5, H.eInsert, 330, H.brModel,
    100, 'AcDbEntity', 8, '0',
    100, 'AcDbBlockReference',
    66, 1,
    2, 'TITLEBLK',
    10, '220.0', 20, '10.0', 30, '0.0',
    41, '1.5', 42, '1.5', 43, '1.0',
    50, '30.0'
  ),
  ...g(
    0, 'ATTRIB', 5, H.eAttrib, 330, H.eInsert,
    100, 'AcDbEntity', 8, 'A-TEXT',
    100, 'AcDbText',
    10, '223.0', 20, '16.0', 30, '0.0',
    40, '5.0',
    1, KO.attValue,
    7, 'HANGUL',
    100, 'AcDbAttribute',
    2, KO.attTag,
    70, 0, 73, 0, 74, 0
  ),
  ...g(0, 'SEQEND', 5, H.eSeqEnd, 330, H.eInsert, 100, 'AcDbEntity', 8, 'A-TEXT'),

  // 8. HATCH — solid fill, one external boundary made of four line edges
  ...g(
    0, 'HATCH', 5, H.eHatch, 330, H.brModel,
    100, 'AcDbEntity', 8, 'A-HATCH', 62, 1,
    100, 'AcDbHatch',
    10, '0.0', 20, '0.0', 30, '0.0',
    210, '0.0', 220, '0.0', 230, '1.0',
    2, 'SOLID',
    70, 1, 71, 0,
    91, 1,
    92, 1,
    93, 4,
    72, 1, 10, '20.0', 20, '20.0', 11, '80.0', 21, '20.0',
    72, 1, 10, '80.0', 20, '20.0', 11, '80.0', 21, '80.0',
    72, 1, 10, '80.0', 20, '80.0', 11, '20.0', 21, '80.0',
    72, 1, 10, '20.0', 20, '80.0', 11, '20.0', 21, '20.0',
    97, 0,
    75, 0, 76, 1,
    47, '1.0', 98, 0
  ),

  // 9. DIMENSION — rotated (linear), geometry lives in block *D1
  ...g(
    0, 'DIMENSION', 5, H.eDim, 330, H.brModel,
    100, 'AcDbEntity', 8, KO.layerDim,
    100, 'AcDbDimension',
    280, 0,
    2, '*D1',
    10, '50.0', 20, '-20.0', 30, '0.0',
    11, '50.0', 21, '-18.0', 31, '0.0',
    70, 32, 71, 5, 42, '100.0',
    1, '',
    3, 'Standard',
    100, 'AcDbAlignedDimension',
    13, '0.0', 23, '0.0', 33, '0.0',
    14, '100.0', 24, '0.0', 34, '0.0',
    100, 'AcDbRotatedDimension',
    50, '0.0'
  ),

  // ---- paper space: main viewport, one drill-down viewport, one line
  ...g(
    0, 'VIEWPORT', 5, H.pViewportMain, 330, H.brPaper,
    100, 'AcDbEntity', 67, 1, 8, '0',
    100, 'AcDbViewport',
    10, '210.0', 20, '148.5', 30, '0.0',
    40, '420.0', 41, '297.0',
    68, 0, 69, 1,
    100, 'AcDbViewport',
    12, '0.0', 22, '0.0',
    13, '0.0', 23, '0.0',
    14, '10.0', 24, '10.0',
    15, '10.0', 25, '10.0',
    16, '0.0', 26, '0.0', 36, '1.0',
    17, '0.0', 27, '0.0', 37, '0.0',
    42, '50.0', 43, '0.0', 44, '0.0', 45, '297.0',
    50, '0.0', 51, '0.0',
    72, 100, 90, 32864, 281, 0, 71, 1, 74, 0,
    110, '0.0', 120, '0.0', 130, '0.0',
    111, '1.0', 121, '0.0', 131, '0.0',
    112, '0.0', 122, '1.0', 132, '0.0',
    345, H.vportActive
  ),
  ...g(
    0, 'VIEWPORT', 5, H.pViewport2, 330, H.brPaper,
    100, 'AcDbEntity', 67, 1, 8, '0',
    100, 'AcDbViewport',
    10, '150.0', 20, '150.0', 30, '0.0',
    40, '240.0', 41, '180.0',
    68, 2, 69, 2,
    100, 'AcDbViewport',
    12, '100.0', 22, '50.0',
    13, '0.0', 23, '0.0',
    14, '10.0', 24, '10.0',
    15, '10.0', 25, '10.0',
    16, '0.0', 26, '0.0', 36, '1.0',
    17, '0.0', 27, '0.0', 37, '0.0',
    42, '50.0', 43, '0.0', 44, '0.0', 45, '220.0',
    50, '0.0', 51, '0.0',
    72, 100, 90, 819232, 281, 0, 71, 1, 74, 0,
    110, '0.0', 120, '0.0', 130, '0.0',
    111, '1.0', 121, '0.0', 131, '0.0',
    112, '0.0', 122, '1.0', 132, '0.0',
    345, H.vportActive
  ),
  ...line(H.pLine, H.brPaper, '0', '10.0', '10.0', '410.0', '10.0', 1),

  ...g(0, 'ENDSEC'),
];

// --------------------------------------------------------------------------
// OBJECTS — root dictionary and two layouts (Model + Layout1)
// --------------------------------------------------------------------------
const plotSettings = (name) =>
  g(
    100, 'AcDbPlotSettings',
    1, '', 2, 'none_device', 4, '', 6, '',
    40, '0.0', 41, '0.0', 42, '0.0', 43, '0.0',
    44, '420.0', 45, '297.0', 46, '0.0', 47, '0.0', 48, '0.0', 49, '0.0',
    140, '0.0', 141, '0.0', 142, '1.0', 143, '1.0',
    70, 688, 72, 1, 73, 0, 74, 5,
    7, '', 75, 16, 147, '1.0', 148, '0.0', 149, '0.0'
  ).concat(name ? [] : []);

const layout = (handle, name, tabOrder, ownerBtr) =>
  g(0, 'LAYOUT', 5, handle, 330, H.dictLayout)
    .concat(plotSettings(name))
    .concat(
      g(
        100, 'AcDbLayout',
        1, name,
        70, 1, 71, tabOrder,
        10, '0.0', 20, '0.0',
        11, '420.0', 21, '297.0',
        12, '0.0', 22, '0.0', 32, '0.0',
        14, '0.0', 24, '0.0', 34, '0.0',
        15, '420.0', 25, '297.0', 35, '0.0',
        146, '0.0',
        13, '0.0', 23, '0.0', 33, '0.0',
        16, '1.0', 26, '0.0', 36, '0.0',
        17, '0.0', 27, '1.0', 37, '0.0',
        76, 0,
        330, ownerBtr
      )
    );

const objects = () => [
  ...g(0, 'SECTION', 2, 'OBJECTS'),
  ...g(
    0, 'DICTIONARY', 5, H.dictRoot, 330, '0',
    100, 'AcDbDictionary', 281, 1,
    3, 'ACAD_GROUP', 350, H.dictGroup,
    3, 'ACAD_LAYOUT', 350, H.dictLayout
  ),
  ...g(0, 'DICTIONARY', 5, H.dictGroup, 330, H.dictRoot, 100, 'AcDbDictionary', 281, 1),
  ...g(
    0, 'DICTIONARY', 5, H.dictLayout, 330, H.dictRoot,
    100, 'AcDbDictionary', 281, 1,
    3, 'Model', 350, H.layoutModel,
    3, 'Layout1', 350, H.layoutPaper
  ),
  ...layout(H.layoutModel, 'Model', 0, H.brModel),
  ...layout(H.layoutPaper, 'Layout1', 1, H.brPaper),
  ...g(0, 'ENDSEC'),
];

// --------------------------------------------------------------------------
// assemble
// --------------------------------------------------------------------------
const build = (acadver, codepage) =>
  [
    ...header(acadver, codepage),
    ...tables(acadver),
    ...blocks(),
    ...entities(),
    ...objects(),
    ...g(0, 'EOF'),
  ].join('\r\n') + '\r\n';

mkdirSync(OUT, { recursive: true });

const r2018 = build('AC1032', 'ANSI_1252');
const r2000 = build('AC1015', 'ANSI_949');

const sha = (buf) => createHash('sha256').update(buf).digest('hex');

const f1 = resolve(OUT, 'F-spike-r2018.dxf');
const f2 = resolve(OUT, 'F-spike-r2000-cp949.dxf');
const b1 = Buffer.from(r2018, 'utf8');
const b2 = iconv.encode(r2000, 'cp949');
writeFileSync(f1, b1);
writeFileSync(f2, b2);

const truth = {
  generator: 'spikes/mlightcad/scripts/make-fixtures.mjs',
  files: {
    'F-spike-r2018.dxf': { acadver: 'AC1032', encoding: 'utf-8', bytes: b1.length, sha256: sha(b1) },
    'F-spike-r2000-cp949.dxf': { acadver: 'AC1015', encoding: 'cp949', bytes: b2.length, sha256: sha(b2) },
  },
  layers: ['0', 'A-WALL', 'A-TEXT', 'A-HATCH', KO.layerDim],
  blockNames: ['*Model_Space', '*Paper_Space', 'TITLEBLK', '*D1'],
  modelSpace: {
    LINE: 1, LWPOLYLINE: 1, CIRCLE: 1, ARC: 1, TEXT: 1,
    MTEXT: 1, INSERT: 1, HATCH: 1, DIMENSION: 1,
    totalTopLevel: 9,
  },
  paperSpace: { VIEWPORT: 2, LINE: 1, totalTopLevel: 3 },
  handles: H,
  korean: KO,
  geometryTruth: {
    lineLength: 200,
    circleRadius: 20,
    circleArea: Math.PI * 400,
    arcRadius: 25,
    arcSweepDeg: 90,
    hatchBoundaryArea: 3600,
    dimensionMeasurement: 100,
  },
};
writeFileSync(resolve(OUT, 'F-spike-truth.json'), JSON.stringify(truth, null, 2) + '\n');

console.log(`wrote ${f1} (${b1.length} bytes, sha256 ${sha(b1).slice(0, 16)}…)`);
console.log(`wrote ${f2} (${b2.length} bytes, sha256 ${sha(b2).slice(0, 16)}…)`);
