# PO File Translator

A web-based tool for translating PO (Portable Object) files into multiple languages using Google Translate.

## Features

- Support for 17+ languages
- Real-time translation progress
- Drag and drop file upload
- Source language auto-detection
- Live translation preview
- Progress tracking
- Downloadable translated files

## Prerequisites

- Python 3.8 or higher
- pip (Python package manager)

## Installation

1. Clone the repository:
```bash
git clone <your-repository-url>
cd translate
```

2. Install required packages:
```bash
pip install flask polib deep-translator
```

3. Create required directories:
```bash
mkdir uploads translated
```

## Usage

1. Start the application:
```bash
python app.py
```

2. Open your web browser and navigate to:
```
http://localhost:5000
```

3. Select source and target languages
4. Upload a PO file by dragging and dropping or using the file picker
5. Click "Translate Now"
6. Wait for the translation to complete
7. Download your translated file

## Supported Languages

- English
- French
- Spanish
- German
- Italian
- Portuguese
- Dutch
- Russian
- Chinese
- Japanese
- Korean
- Arabic
- Hindi
- Turkish
- Polish
- Vietnamese
- Thai

## Project Structure

```
translate/
├── app.py              # Main application file
├── templates/          # HTML templates
│   └── index.html     # Main page template
├── uploads/           # Temporary storage for uploaded files
├── translated/        # Output directory for translated files
├── README.md         # Project documentation
└── .gitignore        # Git ignore file
```

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.