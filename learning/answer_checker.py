import re
from typing import Tuple, List
from difflib import SequenceMatcher
from .models import Question, QuestionOption


class SmartAnswerChecker:
    """Enhanced answer checking with fuzzy matching and intelligent scoring"""
    
    def __init__(self):
        self.similarity_threshold = 0.8
        self.partial_credit_threshold = 0.6
        
    def check_answer(self, question: Question, user_answer: str) -> Tuple[bool, int, dict]:
        """
        Check user answer and return (is_correct, points_earned, feedback)
        """
        if not user_answer or not user_answer.strip():
            return False, 0, {"feedback": "No answer provided"}
        
        user_answer = user_answer.strip()
        
        if question.question_type == 'multiple_choice':
            return self._check_multiple_choice(question, user_answer)
        elif question.question_type == 'true_false':
            return self._check_true_false(question, user_answer)
        elif question.question_type == 'short_answer':
            return self._check_short_answer(question, user_answer)
        elif question.question_type == 'fill_blank':
            return self._check_fill_blank(question, user_answer)
        
        return False, 0, {"feedback": "Unknown question type"}
    
    def _check_multiple_choice(self, question: Question, user_answer: str) -> Tuple[bool, int, dict]:
        """Check multiple choice answer"""
        try:
            # Find the selected option
            selected_option = None
            for option in question.options.all():
                if self._fuzzy_match(option.option_text, user_answer) > 0.9:
                    selected_option = option
                    break
            
            if not selected_option:
                # Try exact match
                selected_option = question.options.filter(option_text__iexact=user_answer).first()
            
            if selected_option:
                if selected_option.is_correct:
                    return True, question.points, {
                        "feedback": "Correct answer!",
                        "selected_option": selected_option.option_text
                    }
                else:
                    correct_option = question.options.filter(is_correct=True).first()
                    return False, 0, {
                        "feedback": f"Incorrect. The correct answer is: {correct_option.option_text if correct_option else 'Not found'}",
                        "selected_option": selected_option.option_text,
                        "correct_option": correct_option.option_text if correct_option else None
                    }
            else:
                return False, 0, {"feedback": "Invalid option selected"}
                
        except Exception as e:
            return False, 0, {"feedback": f"Error checking answer: {str(e)}"}
    
    def _check_true_false(self, question: Question, user_answer: str) -> Tuple[bool, int, dict]:
        """Check true/false answer"""
        user_answer_lower = user_answer.lower().strip()
        correct_answer_lower = question.correct_answer.lower().strip()
        
        # Normalize true/false variations
        true_variations = ['true', 't', 'yes', 'y', '1', 'correct']
        false_variations = ['false', 'f', 'no', 'n', '0', 'incorrect']
        
        user_normalized = None
        if user_answer_lower in true_variations:
            user_normalized = 'true'
        elif user_answer_lower in false_variations:
            user_normalized = 'false'
        
        if user_normalized and user_normalized == correct_answer_lower:
            return True, question.points, {"feedback": "Correct!"}
        elif user_normalized:
            return False, 0, {
                "feedback": f"Incorrect. The correct answer is: {question.correct_answer}",
                "user_answer": user_answer,
                "correct_answer": question.correct_answer
            }
        else:
            return False, 0, {"feedback": "Please answer with True or False"}
    
    def _check_short_answer(self, question: Question, user_answer: str) -> Tuple[bool, int, dict]:
        """Check short answer with intelligent scoring"""
        correct_answer = question.correct_answer.strip()
        user_answer = user_answer.strip()
        
        # Calculate similarity
        similarity = self._fuzzy_match(correct_answer, user_answer)
        
        # Check for exact match
        if similarity >= 0.95:
            return True, question.points, {
                "feedback": "Excellent answer!",
                "similarity": similarity
            }
        
        # Check for high similarity
        elif similarity >= self.similarity_threshold:
            return True, question.points, {
                "feedback": "Correct! Your answer matches the expected response.",
                "similarity": similarity
            }
        
        # Check for partial credit
        elif similarity >= self.partial_credit_threshold:
            partial_points = int(question.points * 0.7)  # 70% credit
            return False, partial_points, {
                "feedback": f"Partially correct. You earned {partial_points} out of {question.points} points.",
                "similarity": similarity,
                "correct_answer": correct_answer
            }
        
        # Check for keyword matching
        else:
            keyword_score = self._check_keywords(correct_answer, user_answer)
            if keyword_score >= 0.5:
                partial_points = int(question.points * 0.5)  # 50% credit
                return False, partial_points, {
                    "feedback": f"Some key concepts identified. You earned {partial_points} out of {question.points} points.",
                    "keyword_score": keyword_score,
                    "correct_answer": correct_answer
                }
        
        return False, 0, {
            "feedback": "Incorrect answer. Please review the material.",
            "similarity": similarity,
            "correct_answer": correct_answer
        }
    
    def _check_fill_blank(self, question: Question, user_answer: str) -> Tuple[bool, int, dict]:
        """Check fill-in-the-blank answer"""
        correct_answer = question.correct_answer.strip()
        user_answer = user_answer.strip()
        
        # Calculate similarity
        similarity = self._fuzzy_match(correct_answer, user_answer)
        
        # More lenient matching for fill-in-the-blank
        if similarity >= 0.8:
            return True, question.points, {
                "feedback": "Correct!",
                "similarity": similarity
            }
        elif similarity >= 0.6:
            partial_points = int(question.points * 0.8)  # 80% credit for close answers
            return False, partial_points, {
                "feedback": f"Very close! You earned {partial_points} out of {question.points} points.",
                "similarity": similarity,
                "correct_answer": correct_answer
            }
        else:
            return False, 0, {
                "feedback": f"Incorrect. The correct answer is: {correct_answer}",
                "similarity": similarity,
                "correct_answer": correct_answer
            }
    
    def _fuzzy_match(self, text1: str, text2: str) -> float:
        """Calculate fuzzy string similarity"""
        if not text1 or not text2:
            return 0.0
        
        # Normalize texts
        text1_norm = self._normalize_text(text1)
        text2_norm = self._normalize_text(text2)
        
        # Calculate similarity using different methods
        sequence_similarity = SequenceMatcher(None, text1_norm, text2_norm).ratio()
        
        # Word-based similarity
        words1 = set(text1_norm.split())
        words2 = set(text2_norm.split())
        
        if words1 and words2:
            word_similarity = len(words1.intersection(words2)) / len(words1.union(words2))
        else:
            word_similarity = 0.0
        
        # Combined similarity (weighted average)
        combined_similarity = (sequence_similarity * 0.6) + (word_similarity * 0.4)
        
        return combined_similarity
    
    def _normalize_text(self, text: str) -> str:
        """Normalize text for comparison"""
        # Convert to lowercase
        text = text.lower()
        
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove punctuation
        text = re.sub(r'[^\w\s]', '', text)
        
        # Strip whitespace
        text = text.strip()
        
        return text
    
    def _check_keywords(self, correct_answer: str, user_answer: str) -> float:
        """Check for important keywords in the answer"""
        # Extract important words (longer than 3 characters)
        correct_words = [word for word in self._normalize_text(correct_answer).split() if len(word) > 3]
        user_words = [word for word in self._normalize_text(user_answer).split() if len(word) > 3]
        
        if not correct_words:
            return 0.0
        
        # Count matching keywords
        matches = 0
        for word in correct_words:
            if word in user_words:
                matches += 1
        
        return matches / len(correct_words)
    
    def get_answer_feedback(self, question: Question, user_answer: str, is_correct: bool, points_earned: int) -> dict:
        """Generate detailed feedback for the answer"""
        feedback = {
            "question_id": question.id,
            "question_type": question.question_type,
            "user_answer": user_answer,
            "correct_answer": question.correct_answer,
            "is_correct": is_correct,
            "points_earned": points_earned,
            "max_points": question.points,
            "explanation": question.explanation,
        }
        
        if question.question_type == 'multiple_choice':
            correct_option = question.options.filter(is_correct=True).first()
            feedback["correct_option"] = correct_option.option_text if correct_option else None
            feedback["all_options"] = [opt.option_text for opt in question.options.all()]
        
        return feedback