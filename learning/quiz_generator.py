import re
import random
from typing import List, Dict, Tuple
from django.utils.text import slugify
from .models import Document, Quiz, Question, QuestionOption


class QuizGenerator:
    """Service for generating quiz questions from document text"""
    
    def __init__(self, document: Document):
        self.document = document
        self.text = document.extracted_text
        self.sentences = self._split_into_sentences()
        self.paragraphs = self._split_into_paragraphs()
        
    def _split_into_sentences(self) -> List[str]:
        """Split text into sentences"""
        if not self.text:
            return []
        
        # Simple sentence splitting (can be improved with NLTK)
        sentences = re.split(r'[.!?]+', self.text)
        sentences = [s.strip() for s in sentences if s.strip() and len(s.strip()) > 10]
        return sentences
    
    def _split_into_paragraphs(self) -> List[str]:
        """Split text into paragraphs"""
        if not self.text:
            return []
        
        paragraphs = self.text.split('\n\n')
        paragraphs = [p.strip() for p in paragraphs if p.strip() and len(p.strip()) > 50]
        return paragraphs
    
    def generate_quiz(self, title: str, description: str, difficulty: str, 
                     num_questions: int, time_limit: int, created_by) -> Quiz:
        """Generate a complete quiz with questions"""
        
        # Create the quiz
        quiz = Quiz.objects.create(
            title=title,
            description=description,
            document=self.document,
            created_by=created_by,
            difficulty=difficulty,
            time_limit_minutes=time_limit,
            total_questions=num_questions
        )
        
        # Generate questions
        questions = self._generate_questions(num_questions, difficulty)
        
        # Create question objects
        for i, question_data in enumerate(questions):
            question = Question.objects.create(
                quiz=quiz,
                question_text=question_data['question'],
                question_type=question_data['type'],
                correct_answer=question_data['correct_answer'],
                explanation=question_data.get('explanation', ''),
                points=question_data.get('points', 1),
                order=i + 1
            )
            
            # Create options for multiple choice questions
            if question_data['type'] == 'multiple_choice' and 'options' in question_data:
                for j, option in enumerate(question_data['options']):
                    QuestionOption.objects.create(
                        question=question,
                        option_text=option['text'],
                        is_correct=option['is_correct'],
                        order=j + 1
                    )
        
        return quiz
    
    def _generate_questions(self, num_questions: int, difficulty: str) -> List[Dict]:
        """Generate different types of questions"""
        questions = []
        
        # Determine question type distribution based on difficulty
        if difficulty == 'easy':
            type_distribution = {
                'multiple_choice': 0.4,
                'true_false': 0.4,
                'fill_blank': 0.2
            }
        elif difficulty == 'medium':
            type_distribution = {
                'multiple_choice': 0.3,
                'true_false': 0.3,
                'short_answer': 0.2,
                'fill_blank': 0.2
            }
        else:  # hard
            type_distribution = {
                'multiple_choice': 0.2,
                'true_false': 0.2,
                'short_answer': 0.4,
                'fill_blank': 0.2
            }
        
        # Generate questions based on distribution
        for _ in range(num_questions):
            question_type = self._choose_question_type(type_distribution)
            
            if question_type == 'multiple_choice':
                question = self._generate_multiple_choice()
            elif question_type == 'true_false':
                question = self._generate_true_false()
            elif question_type == 'short_answer':
                question = self._generate_short_answer()
            elif question_type == 'fill_blank':
                question = self._generate_fill_blank()
            else:
                question = self._generate_multiple_choice()  # fallback
            
            if question:
                questions.append(question)
        
        return questions
    
    def _choose_question_type(self, distribution: Dict[str, float]) -> str:
        """Choose question type based on probability distribution"""
        rand = random.random()
        cumulative = 0
        
        for question_type, probability in distribution.items():
            cumulative += probability
            if rand <= cumulative:
                return question_type
        
        return 'multiple_choice'  # fallback
    
    def _generate_multiple_choice(self) -> Dict:
        """Generate a multiple choice question"""
        if not self.sentences:
            return None
        
        # Select a sentence with important information
        sentence = self._select_informative_sentence()
        if not sentence:
            return None
        
        # Extract key terms
        key_terms = self._extract_key_terms(sentence)
        if not key_terms:
            return None
        
        # Choose a term to ask about
        target_term = random.choice(key_terms)
        
        # Create question by replacing the term
        question_text = sentence.replace(target_term, "______")
        question_text = f"What word or phrase best completes this statement?\n\n{question_text}"
        
        # Generate options
        correct_option = target_term
        incorrect_options = self._generate_distractors(target_term, 3)
        
        # Combine and shuffle options
        all_options = [{'text': correct_option, 'is_correct': True}]
        for option in incorrect_options:
            all_options.append({'text': option, 'is_correct': False})
        
        random.shuffle(all_options)
        
        return {
            'type': 'multiple_choice',
            'question': question_text,
            'correct_answer': correct_option,
            'options': all_options,
            'explanation': f"The correct answer is '{correct_option}' based on the context in the document.",
            'points': 2
        }
    
    def _generate_true_false(self) -> Dict:
        """Generate a true/false question"""
        if not self.sentences:
            return None
        
        sentence = self._select_informative_sentence()
        if not sentence:
            return None
        
        # Randomly decide if this should be true or false
        is_true = random.choice([True, False])
        
        if is_true:
            question_text = f"True or False: {sentence}"
            correct_answer = "True"
            explanation = "This statement is true according to the document."
        else:
            # Modify the sentence to make it false
            modified_sentence = self._modify_sentence_for_false(sentence)
            question_text = f"True or False: {modified_sentence}"
            correct_answer = "False"
            explanation = "This statement is false. The correct information is in the document."
        
        return {
            'type': 'true_false',
            'question': question_text,
            'correct_answer': correct_answer,
            'explanation': explanation,
            'points': 1
        }
    
    def _generate_short_answer(self) -> Dict:
        """Generate a short answer question"""
        if not self.sentences:
            return None
        
        sentence = self._select_informative_sentence()
        if not sentence:
            return None
        
        # Extract key terms and create a question
        key_terms = self._extract_key_terms(sentence)
        if not key_terms:
            return None
        
        target_term = random.choice(key_terms)
        
        # Create question asking for the key term
        question_patterns = [
            f"According to the document, what is {target_term.lower()}?",
            f"Define or explain {target_term.lower()} as mentioned in the text.",
            f"What does the document say about {target_term.lower()}?",
        ]
        
        question_text = random.choice(question_patterns)
        
        return {
            'type': 'short_answer',
            'question': question_text,
            'correct_answer': target_term,
            'explanation': f"The answer can be found in the context: {sentence}",
            'points': 3
        }
    
    def _generate_fill_blank(self) -> Dict:
        """Generate a fill-in-the-blank question"""
        if not self.sentences:
            return None
        
        sentence = self._select_informative_sentence()
        if not sentence:
            return None
        
        # Extract key terms
        key_terms = self._extract_key_terms(sentence)
        if not key_terms:
            return None
        
        # Choose term to blank out
        target_term = random.choice(key_terms)
        
        # Create question with blank
        question_text = sentence.replace(target_term, "______")
        question_text = f"Fill in the blank:\n\n{question_text}"
        
        return {
            'type': 'fill_blank',
            'question': question_text,
            'correct_answer': target_term,
            'explanation': f"The correct answer is '{target_term}'.",
            'points': 2
        }
    
    def _select_informative_sentence(self) -> str:
        """Select a sentence that contains useful information"""
        if not self.sentences:
            return None
        
        # Filter sentences by length and content
        good_sentences = []
        for sentence in self.sentences:
            if (20 <= len(sentence.split()) <= 50 and 
                not sentence.lower().startswith(('the', 'this', 'that', 'it')) and
                any(char.isupper() for char in sentence)):  # Has proper nouns
                good_sentences.append(sentence)
        
        if not good_sentences:
            good_sentences = [s for s in self.sentences if len(s.split()) >= 10]
        
        return random.choice(good_sentences) if good_sentences else None
    
    def _extract_key_terms(self, sentence: str) -> List[str]:
        """Extract key terms from a sentence"""
        # Simple approach: look for capitalized words and important terms
        words = sentence.split()
        key_terms = []
        
        for word in words:
            # Remove punctuation
            clean_word = re.sub(r'[^\w\s]', '', word)
            
            # Look for proper nouns, numbers, and important terms
            if (clean_word and 
                (clean_word[0].isupper() or 
                 clean_word.isdigit() or 
                 len(clean_word) > 6)):
                key_terms.append(clean_word)
        
        # Also look for multi-word terms
        for i in range(len(words) - 1):
            if words[i][0].isupper() and words[i+1][0].isupper():
                term = f"{words[i]} {words[i+1]}"
                term = re.sub(r'[^\w\s]', '', term)
                if term:
                    key_terms.append(term)
        
        return list(set(key_terms))  # Remove duplicates
    
    def _generate_distractors(self, correct_answer: str, num_distractors: int) -> List[str]:
        """Generate plausible incorrect options"""
        distractors = []
        
        # Simple approach: generate variations of the correct answer
        variations = [
            correct_answer.upper(),
            correct_answer.lower(),
            correct_answer + "s",
            "Not " + correct_answer,
            correct_answer.replace("a", "e") if "a" in correct_answer else correct_answer + "ing",
        ]
        
        # Add some generic distractors
        generic_distractors = [
            "None of the above",
            "All of the above",
            "Cannot be determined",
            "Not mentioned in the text",
        ]
        
        all_distractors = variations + generic_distractors
        
        # Remove the correct answer if it appears in variations
        all_distractors = [d for d in all_distractors if d.lower() != correct_answer.lower()]
        
        # Select random distractors
        selected = random.sample(all_distractors, min(num_distractors, len(all_distractors)))
        
        # Pad with generic options if needed
        while len(selected) < num_distractors:
            selected.append(f"Option {len(selected) + 1}")
        
        return selected[:num_distractors]
    
    def _modify_sentence_for_false(self, sentence: str) -> str:
        """Modify a sentence to make it false"""
        # Simple modifications
        modifications = [
            ("is", "is not"),
            ("are", "are not"),
            ("was", "was not"),
            ("were", "were not"),
            ("can", "cannot"),
            ("will", "will not"),
            ("should", "should not"),
        ]
        
        for original, replacement in modifications:
            if f" {original} " in sentence:
                return sentence.replace(f" {original} ", f" {replacement} ")
        
        # If no simple modification works, add "not" after the first verb
        words = sentence.split()
        for i, word in enumerate(words):
            if word.lower() in ["is", "are", "was", "were", "can", "will", "should", "has", "have"]:
                words.insert(i + 1, "not")
                return " ".join(words)
        
        # Fallback: just add "not" at the beginning
        return f"It is not true that {sentence.lower()}"